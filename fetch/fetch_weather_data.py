#!/usr/bin/env python3
"""
This file is for fetching BMKG weather data through public API from https://api.bmkg.go.id/publik/prakiraan-cuaca.
Fetching is done one-by-one based on region code "adm4" and BMKG restricts access by 60 request per minute per IP.
"""

import time
import os
import sys
import requests
import pandas as pd
import numpy as np
from pathlib import Path
import traceback
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.db import get_conn, get_current_jakarta_time

API_URL = "https://api.bmkg.go.id/publik/prakiraan-cuaca"  # BMKG open weather forecast API endpoint
REFERENCE_FILE = BASE_DIR / "jakarta_reference.csv" # output from build_jakarta_preference.py, containing list of adm4 codes to fetch forecasts for
WEATHER_TABLE = "ward_weather_table" # table name to save forecasts into
CITY_SUMMARY_TABLE = "city_summary_table"

def get_refresh_interval_hours() -> float:
    return float(os.getenv("REFRESH_INTERVAL_HOURS", "36"))


def chunk_rows(rows: list[tuple[Any, ...]], chunk_size: int = 500) -> list[list[tuple[Any, ...]]]:
    return [rows[idx: idx + chunk_size] for idx in range(0, len(rows), chunk_size)] # chunk the rows into smaller batches to avoid hitting database limits on number of rows per insert

# function to add a timestamp column indicating when the data was fetched
def add_fetched_at(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["fetched_at"] = get_current_jakarta_time() # get local Jakarta time
    return df

# note: as far as I know (CMIIW), BMKG does not provide a bulk API endpoint for multiple adm4 codes at once,
# so it will loop over the adm4 codes and fetch them one by one
def fetch_bmkg_by_adm4(
    adm4: str,
    max_retries: int = 3,
    timeout: int = 30,
    backoff_seconds: float = 2.0) -> dict:
    """Fetch BMKG JSON for one adm4 with retry plus backoff."""
    last_exc = None # to store the last exception in case all retries fail

    # loop with retries and backoff in case of transient errors or rate limits
    for attempt in range(1, max_retries + 1):

        try:
            response = requests.get(
                API_URL,
                params={"adm4": adm4},
                timeout=timeout # second, set a timeout to avoid hanging indefinitely if BMKG server is not responding
            )
            response.raise_for_status() # raise Error if the request failed
            return response.json()
        
        except requests.exceptions.RequestException as exc:
            last_exc = exc

            # if this was the last attempt, print the exception and re-raise it to be handled by the caller
            if attempt == max_retries:
                print(f"BMKG fetch failed for adm4={adm4} after {max_retries} attempts")
                print(exc)
                raise
            
            # calculate backoff time with increasing time with attempts, so wait longer between each retry attempt
            sleep_for = backoff_seconds * (2 ** (attempt - 1))
            print(
                f"BMKG fetch failed for adm4={adm4} on attempt {attempt}/{max_retries}: "
                f"{exc}. Retrying in {sleep_for:.1f} s"
            )
            time.sleep(sleep_for)

    raise last_exc # if used up all retries, raise the last exception encountered

# the API returns nested JSON with multiple forecast timestamps per adm4, 
# but I want one row per timestamp per adm4 for easier analysis and visualization
def flatten_forecast(data: dict, adm4: str) -> pd.DataFrame:
    rows = []

    data_list = data.get("data", [])
    if not data_list:
        return pd.DataFrame() # return empty DataFrame if no data

    record = data_list[0]
    daily_groups = record.get("cuaca", []) # for weather forecasts
    location_data = record.get("lokasi", {}) # for location metadata

    for daily_group in daily_groups:
        for item in daily_group:
            rows.append(
                {
                    "adm4": adm4, # regional code
                    "desa_kelurahan": location_data.get("desa"),
                    "kecamatan": location_data.get("kecamatan"),
                    "kota_kabupaten": location_data.get("kotkab"),
                    "provinsi": location_data.get("provinsi"),
                    "latitude": pd.to_numeric(location_data.get("lat"), errors="coerce"),
                    "longitude": pd.to_numeric(location_data.get("lon"), errors="coerce"),
                    "timezone": location_data.get("timezone"),
                    "local_datetime": item.get("local_datetime"),
                    "temperature_c": pd.to_numeric(item.get("t"), errors="coerce"), # temperature in celsius
                    "humidity_ptg": pd.to_numeric(item.get("hu"), errors="coerce"), # humidity in percentage
                    "weather_desc": item.get("weather_desc_en"), # weather description in English
                }
            )

    df = pd.DataFrame(rows)

    if not df.empty:

        # converting datetime columns to pandas datetime type, Timestamp, for easier manipulation later
        df["local_datetime"] = pd.to_datetime(df["local_datetime"], errors="coerce")

        # sort by time, important fort interpolation later
        df = df.sort_values("local_datetime").reset_index(drop=True)

    return df

# IMPORTANT!!!
# here, I set a fixed time grid to be 23:00, 02:00, 05:00, 08:00, 11:00, 14:00, 17:00, 20:00
# ceiling function will round up to the next timestamp on this cycle, while floor function will round down to the previous timestamp on this cycle
def snap_to_target_cycle(ts: pd.Timestamp, how: str = "ceil") -> pd.Timestamp:
    """
    Snap a timestamp to the target 3-hour cycle:
    23:00, 02:00, 05:00, 08:00, ...

    Parameters
    ----------
    ts : pd.Timestamp
        Input timestamp.
    how : {"ceil", "floor"}
        - "ceil": round up to the next valid cycle timestamp
        - "floor": round down to the previous valid cycle timestamp
    """
    ts = pd.Timestamp(ts)
    cycle_hours = [23, 2, 5, 8, 11, 14, 17, 20] # cycle anchored at 23:00
    day_start = ts.normalize()

    # candidate times for previous/current/next day
    candidates = []
    for offset_day in [-1, 0, 1]:
        base_day = day_start + pd.Timedelta(days=offset_day)
        for h in cycle_hours:
            candidates.append(base_day + pd.Timedelta(hours=h))

    candidates = sorted(candidates)

    if how == "ceil":
        for c in candidates:
            if c >= ts:
                return c

    elif how == "floor":
        for c in reversed(candidates):
            if c <= ts:
                return c
            
    # here, rows that already have timestamps exactly on the cycle will be unchanged, 
    # because the cycle time will be both a valid ceiling and floor, 
    # and the ceiling function will return it immediately

    else:
        raise ValueError("how must be either 'ceil' or 'floor'")

    return candidates[-1] if how == "ceil" else candidates[0]

# the function finds the largest time interval shared by all regions and builds a 3-hour timestamp grid that every region can be aligned to
def build_common_target_grid(df: pd.DataFrame) -> pd.DatetimeIndex:
    """
    Build a common 3-hour grid shared by all adm4 regions,
    restricted to the overlapping time window so every region
    has values at every timestamp.
    """
    grouped = df.groupby("adm4")["local_datetime"] # group by adm4 and get the local_datetime column for each group

    # find the min and max timestamp for each adm4
    raw_starts = grouped.min()
    raw_ends = grouped.max()

    # the common grid will be from the latest of the start times (ceiling) to the earliest of the end times (floor)
    common_start = max(snap_to_target_cycle(ts, "ceil") for ts in raw_starts)
    common_end   = min(snap_to_target_cycle(ts, "floor") for ts in raw_ends)

    if common_end < common_start:
        raise ValueError(
            f"No overlapping common 3-hour window found. "
            f"common_start={common_start}, common_end={common_end}"
        )

    return pd.date_range(start=common_start, end=common_end, freq="3h")

# align every region's forecast to the same timestamps so they can be compared and visualized together
def interpolate_one_adm4_to_grid(df_one: pd.DataFrame, target_grid: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Interpolate one location onto the common target grid.
    Numeric columns are linearly interpolated in time.
    Categorical columns are taken from nearest known value.

    df_one is the forecast DataFrame for one adm4, with original timestamps from BMKG.
    target_grid is the common 3-hour grid that every adm4 will be aligned to.
    """
    if df_one.empty:
        return df_one.copy()

    # ensure sorted by time and remove duplicates, important for interpolation to work correctly
    df_one = df_one.sort_values("local_datetime").drop_duplicates("local_datetime").copy()
    df_one = df_one.set_index("local_datetime")

    # union index so pandas can interpolate between original timestamps
    union_index = df_one.index.union(target_grid).sort_values()
    work = df_one.reindex(union_index) # create new rows for the target grid timestamps

    # metadata constant per adm4 (parameter values that do not change over time)
    static_cols = [
        "adm4", "desa_kelurahan", "kecamatan", "kota_kabupaten", "provinsi",
        "latitude", "longitude", "timezone"
    ]
    for col in static_cols:
        work[col] = work[col].ffill().bfill() # fill missing values with nearest known value

    # time interpolation for weather variables
    # note that the interpolation function will only fill NaN values between known values
    # using time method for interpolation, see padas.DataFrame.interpolate documentation
    # linear interpolation is not used because the time interval between the original timestamps and the target grid is not guaranteed to be consistent
    # limit_direction="both" allows interpolation in both directions
    for col in ["temperature_c", "humidity_ptg"]:
        work[col] = work[col].interpolate(method="time", limit_direction="both") 

    # categorical / descriptive fields
    work["weather_desc"] = work["weather_desc"].ffill().bfill()

    out = work.loc[target_grid].reset_index().rename(columns={"index": "local_datetime"}) # keep only the target grid timestamps

    # compute heat index and risk level for each row
    out["heat_index_c"] = out.apply(
        lambda row: compute_heat_index_c(row["temperature_c"], row["humidity_ptg"]),
        axis=1,
    )
    out["risk_level"] = out["heat_index_c"].apply(classify_heat_risk)

    return out[
        [
            "adm4", "desa_kelurahan", "kecamatan", "kota_kabupaten", "provinsi",
            "latitude", "longitude", "timezone", "local_datetime",
            "temperature_c", "humidity_ptg", "heat_index_c", "risk_level",
            "weather_desc",
        ]
    ]

# wrapper function for the interpolation
def align_all_forecasts_to_common_grid(df: pd.DataFrame) -> pd.DataFrame:
    """
    Align every adm4 forecast to one shared 3-hour grid
    """
    if df.empty:
        return df.copy()

    target_grid = build_common_target_grid(df)

    # loop over each adm4 group and interpolate to the target grid, then concatenate all results together
    aligned_frames = []
    for adm4, grp in df.groupby("adm4", sort=True):
        aligned_frames.append(interpolate_one_adm4_to_grid(grp, target_grid))

    out = pd.concat(aligned_frames, ignore_index=True)
    out = out.sort_values(["local_datetime", "adm4"]).reset_index(drop=True) # sort by time first, then by adm4 for easier analysis and visualization later
    return out

# ###############
# Functions For Heat Index Computation
# see https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
# ##############

# convert temperature from Celsius to Fahrenheit
def c_to_f(temp_c: float) -> float:
    return (temp_c * 9 / 5) + 32

# convert temperature from Fahrenheit to Celsius
def f_to_c(temp_f: float) -> float:
    return (temp_f - 32) * 5 / 9

# compute heat index in Celsius using the formula from US National Weather Service, with adjustments for low humidity and high humidity
# valid at least for US subtropical conditions
def compute_heat_index_c(temp_c: float, rh: float) -> float:
    if pd.isna(temp_c) or pd.isna(rh):
        return np.nan

    T = c_to_f(temp_c)
    RH = rh

    hi_simple = 0.5 * (T + 61.0 + ((T - 68.0) * 1.2) + (RH * 0.094))
    hi_initial = 0.5 * (hi_simple + T)

    if hi_initial < 80:
        return f_to_c(hi_initial)

    HI = (
        -42.379
        + 2.04901523 * T
        + 10.14333127 * RH
        - 0.22475541 * T * RH
        - 0.00683783 * T * T
        - 0.05481717 * RH * RH
        + 0.00122874 * T * T * RH
        + 0.00085282 * T * RH * RH
        - 0.00000199 * T * T * RH * RH
    )

    if RH < 13 and 80 <= T <= 112: # adjustment for low humidity
        adjustment = ((13 - RH) / 4) * np.sqrt((17 - abs(T - 95.0)) / 17)
        HI -= adjustment
    elif RH > 85 and 80 <= T <= 87: # adjustment for high humidity
        adjustment = ((RH - 85) / 10) * ((87 - T) / 5)
        HI += adjustment

    return f_to_c(HI)

# classify heat risk level based on heat index thresholds, using the same thresholds as the US National Weather Service
# see https://www.weather.gov/ama/heatindex#:~:text=Table_title:%20What%20is%20the%20heat%20index?%20Table_content:,the%20body:%20Heat%20stroke%20highly%20likely%20%7C
def classify_heat_risk(heat_index_c: float) -> str:
    if pd.isna(heat_index_c):
        return np.nan
    if heat_index_c < 26.7:
        return "Lower Risk"
    elif heat_index_c < 32.2:
        return "Caution"
    elif heat_index_c < 39.4:
        return "Extreme Caution"
    elif heat_index_c < 51.1:
        return "Danger"
    else:
        return "Extreme Danger"
    

    
# loading the reference file with the list of adm4 codes and their corresponding location names, 
# used to fetch forecasts and also to save metadata in the database
def load_reference_csv(path: Path) -> pd.DataFrame:
    ref_df = pd.read_csv(path, dtype=str)

    required_cols = [
        "adm4",
        "desa_kelurahan",
        "kecamatan",
        "kota_kabupaten",
        "provinsi",
    ]
    missing = [c for c in required_cols if c not in ref_df.columns]
    if missing:
        raise ValueError(f"Reference file is missing columns: {missing}") # raise value error if required columns are missing

    ref_df["adm4"] = ref_df["adm4"].astype(str).str.strip() # ensure adm4 is string and remove any leading/trailing whitespace
    ref_df = ref_df.dropna(subset=["adm4"]).drop_duplicates(subset=["adm4"]) # drop rows with missing adm4 and duplicate adm4, because adm4 is the key for fetching forecasts and saving to database, so it must be unique and not null
    return ref_df.reset_index(drop=True)

def fetch_all_jakarta_forecasts(ref_df: pd.DataFrame, 
                                sleep_seconds: float = 1.01, 
                                region_list: list[str] = None) -> pd.DataFrame:
    """
    Loop over all adm4 codes in the reference file and combine forecasts.
    sleep_seconds is used to stay polite and well under BMKG rate limits.
    """
    all_frames = []
    total = len(ref_df)
    
    # if region_list is provided, filter the reference DataFrame to only include those adm4 codes, otherwise fetch for all adm4 codes in the reference file
    if region_list is not None:
        ref_df = ref_df[ref_df["adm4"].isin(region_list)]

    for i, row in ref_df.iterrows():
        adm4 = row["adm4"]
        print(
            f"[{i + 1}/{total}] Fetching {adm4} - "
            f"{row['desa_kelurahan']}, {row['kecamatan']}, {row['kota_kabupaten']} ..."
        )

        try:
            data = fetch_bmkg_by_adm4(adm4)
            df_one = flatten_forecast(data, adm4=adm4)

            if df_one.empty:
                print(f"No forecast rows returned for adm4={adm4}")
            else:
                all_frames.append(df_one)

        except Exception:
            print(f"Error while processing adm4={adm4}")
            traceback.print_exc()

        time.sleep(sleep_seconds) # sleep between requests to avoid hitting rate limits

    if not all_frames:
        print("No forecast data fetched for any region.")
        return pd.DataFrame()

    raw_df = pd.concat(all_frames, ignore_index=True)

    # perform aligning and interpolation to the common grid
    aligned_df = align_all_forecasts_to_common_grid(raw_df)

    print(f"Combined aligned forecast rows: {len(aligned_df)}")
    return aligned_df


# this function ensures that the target table used to store the forecasts exists before writing data into it
def create_weather_table_if_needed(conn) -> None:
    conn.cursor().execute(
        f"""
        CREATE TABLE IF NOT EXISTS {WEATHER_TABLE} (
            adm4 VARCHAR(32) NOT NULL,
            desa_kelurahan VARCHAR(255),
            kecamatan VARCHAR(255),
            kota_kabupaten VARCHAR(255),
            provinsi VARCHAR(255),
            latitude DOUBLE,
            longitude DOUBLE,
            timezone VARCHAR(64),
            local_datetime DATETIME NOT NULL,
            temperature_c DOUBLE,
            humidity_ptg DOUBLE,
            heat_index_c DOUBLE,
            risk_level VARCHAR(64),
            weather_desc VARCHAR(255),
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (local_datetime, adm4),
            INDEX idx_weather_time (local_datetime),
            INDEX idx_weather_region_time (adm4, local_datetime)
        )
        """
    )
    conn.commit()



def get_last_refresh_time(conn) -> pd.Timestamp | None:
    df = pd.read_sql_query(
        f"""
        SELECT MAX(fetched_at) AS fetched_at
        FROM {WEATHER_TABLE}
        WHERE fetched_at IS NOT NULL
        """,
        conn,
    )
    if df.empty:
        return None

    ts = pd.to_datetime(df.iloc[0]["fetched_at"], errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def should_refresh(conn, min_interval_hours: float | None = None) -> tuple[bool, pd.Timestamp | None]:
    min_interval_hours = get_refresh_interval_hours() if min_interval_hours is None else min_interval_hours
    last_refresh = get_last_refresh_time(conn) # get the last refresh time from fetched_at column

    if last_refresh is None:
        return True, None # if there is no record of last refresh, refresh

    elapsed = get_current_jakarta_time() - last_refresh
    return elapsed >= pd.Timedelta(hours=min_interval_hours), last_refresh


# saving to MySQL database by replacing the existing contents with the latest fetched dataset
def save_to_mysql(df: pd.DataFrame, conn) -> None:

    if df.empty:
        print("DataFrame is empty. Nothing to save.")
        return

    create_weather_table_if_needed(conn)

    weather_df = df.copy()
    weather_df["local_datetime"] = pd.to_datetime(weather_df["local_datetime"]).dt.to_pydatetime()
    weather_df["fetched_at"] = pd.to_datetime(weather_df["fetched_at"]).dt.to_pydatetime()

    weather_rows = [ # extract relevant columns
        (
            row["adm4"],
            row["desa_kelurahan"],
            row["kecamatan"],
            row["kota_kabupaten"],
            row["provinsi"],

            # lat/lon not used
            # None if pd.isna(row["latitude"]) else float(row["latitude"]),
            # None if pd.isna(row["longitude"]) else float(row["longitude"]),

            row["timezone"],
            row["local_datetime"],
            None if pd.isna(row["temperature_c"]) else float(row["temperature_c"]),
            None if pd.isna(row["humidity_ptg"]) else float(row["humidity_ptg"]),
            None if pd.isna(row["heat_index_c"]) else float(row["heat_index_c"]),
            row["risk_level"],
            row["weather_desc"],
            row["fetched_at"],
        )
        for _, row in weather_df.iterrows()
    ]

    # rows are inserted in batches after clearing the existing table so that each refresh fully replaces the previous snapshot
    weather_sql = f"""
        INSERT INTO {WEATHER_TABLE} (
            adm4, desa_kelurahan, kecamatan, kota_kabupaten, provinsi,
            timezone, local_datetime,
            temperature_c, humidity_ptg, heat_index_c, risk_level,
            weather_desc, fetched_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    cursor = conn.cursor()
    try:
        cursor.execute(f"DELETE FROM {WEATHER_TABLE}")
        for rows_chunk in chunk_rows(weather_rows): # execute the insert in chunks to avoid hitting database limits on number of rows per batch
            cursor.executemany(weather_sql, rows_chunk)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def save_forecasts(df: pd.DataFrame) -> None:
    conn = get_conn()
    try:
        save_to_mysql(df, conn)
    finally:
        conn.close()

# main function to run the whole refresh process
def run_refresh_job(
    sleep_seconds: float = 1.01, # sleep to stay under BMKG API rate limit
    region_list: list[str] | None = None, # list of adm4 codes; if None, fetch for all codes
) -> dict[str, Any]:
    ref_df = load_reference_csv(REFERENCE_FILE) # contains list of adm4 Jakarta codes and their location names
    print(f"Loaded {len(ref_df)} reference locations from {REFERENCE_FILE}")

    print("")
    print("Configured database backend: mysql")
    print("")
    conn = get_conn()
    try:
        create_weather_table_if_needed(conn)
        should_run, last_refresh = should_refresh(conn) # determine whether to run refresh
    finally:
        conn.close()

    if not should_run: # skipping refresh
        print(
            f"Skipping refresh because the latest successful sync at {last_refresh} is still within {get_refresh_interval_hours():.1f} hours."
        )
        return {
            "status": "skipped",
            "backend": "mysql",
            "last_refresh": None if last_refresh is None else str(last_refresh),
            "reason": f"Latest refresh is newer than {get_refresh_interval_hours():.1f} hours.",
        }

    df = fetch_all_jakarta_forecasts(ref_df, sleep_seconds=sleep_seconds, region_list=region_list)
    # set region_list to a list of adm4 codes desired, otherwise set to None to fetch all regions in the reference file

    if df.empty:
        print("No forecast data fetched. Nothing saved.")
        return {"status": "empty", "backend": "mysql", "rows": 0}

    df = add_fetched_at(df)
    save_forecasts(df) # save to MySQL

    return {
        "status": "success",
        "backend": "mysql",
        "rows": int(len(df)),
        "fetched_at": str(df["fetched_at"].iloc[0]),
    }

def main():
    print("")
    print("========= BMKG refresh job started =========")
    print("")

    try:
        result = run_refresh_job(sleep_seconds=1.01, region_list=None)
        if result["status"] in {"empty", "skipped"}:
            print("")
            print(f"Refresh finished with status={result['status']}")
            print("")
            return 0

        print("")
        print("========= BMKG refresh job completed successfully =========")
        print("")

        return 0
    
    except Exception:
        print("")
        print("========= BMKG refresh job failed =========")
        traceback.print_exc()
        print("")
        return 1

if __name__ == "__main__":
    raise SystemExit(main()) # SystemExit for cron
