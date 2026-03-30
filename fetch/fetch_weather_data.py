#!/usr/bin/env python3
"""
This file is for fetching BMKG weather data through public API from https://api.bmkg.go.id/publik/prakiraan-cuaca.
Fetching is done one-by-one based on region code "adm4" and BMKG restricts access by 60 request per minute per IP.
"""

import time
import requests
import pandas as pd
import numpy as np
import sqlite3
from pathlib import Path
import logging

BASE_DIR = Path(__file__).resolve().parents[1]

API_URL = "https://api.bmkg.go.id/publik/prakiraan-cuaca"  # BMKG open weather forecast API endpoint
REFERENCE_FILE = BASE_DIR / "jakarta_reference.csv" # output from build_jakarta_preference.py, containing list of adm4 codes to fetch forecasts for
DB_PATH = BASE_DIR / "tables" / "heat_risk.db" # SQLite database file to save forecasts into
WEATHER_TABLE = "ward_weather_table" # SQLite table name to save forecasts into
CITY_SUMMARY_TABLE = "city_summary_table"
LOG_DIR = BASE_DIR / "logs" # directory to save log files, will be created if it does not exist
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(format='%(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_logging() -> None:
    log_file = LOG_DIR / "bmkg_refresh.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

# function to add a timestamp column indicating when the data was fetched
# for tracking data freshness and debugging
def add_fetched_at(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["fetched_at"] = pd.Timestamp.now(tz="Asia/Jakarta") # get local Jakarta time
    return df

# note: as far as I know (CMIIW), BMKG does not provide a bulk API endpoint for multiple adm4 codes at once,
# so I will loop over the adm4 codes and fetch them one by one
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

            # if this was the last attempt, log the exception and re-raise it to be handled by the caller
            if attempt == max_retries:
                logger.exception(
                    "BMKG fetch failed for adm4=%s after %s attempts",
                    adm4,
                    max_retries,
                )
                raise
            
            # calculate backoff time with increasing time with attempts, so wait longer between each retry attempt
            sleep_for = backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "BMKG fetch failed for adm4=%s on attempt %s/%s: %s. Retrying in %.1f s",
                adm4,
                attempt,
                max_retries,
                exc,
                sleep_for,
            )
            time.sleep(sleep_for)

    raise last_exc # if used up all retries, raise the last exception encountered

# the API returns nested JSON with multiple forecast timestamps per adm4, 
# but I want one row per timestamp per adm4 for easier analysis and visualization
def flatten_forecast(data: dict, adm4: str) -> pd.DataFrame:
    """
    Flatten BMKG nested JSON into tabular DataFrame
    Keeps one row per forecast timestamp for one adm4
    """
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

# one of the most important functions, to align every region's forecast to the same timestamps so they can be compared and visualized together
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

    if RH < 13 and 80 <= T <= 112:
        adjustment = ((13 - RH) / 4) * np.sqrt((17 - abs(T - 95.0)) / 17)
        HI -= adjustment
    elif RH > 85 and 80 <= T <= 87:
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
    
# ########
# ######

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

# main function to loop over all adm4 codes in the reference file, fetch forecasts, flatten and align them, then save to SQLite database
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
        logger.info(
            "[%s/%s] Fetching %s - %s, %s, %s ...",
            i + 1,
            total,
            adm4,
            row["desa_kelurahan"],
            row["kecamatan"],
            row["kota_kabupaten"],
        )

        try:
            data = fetch_bmkg_by_adm4(adm4)
            df_one = flatten_forecast(data, adm4=adm4)

            if df_one.empty:
                logger.warning("No forecast rows returned for adm4=%s", adm4)
            else:
                all_frames.append(df_one)
                # logger.info("Fetched %s rows for adm4=%s", len(df_one), adm4)

        except Exception:
            logger.exception("Error while processing adm4=%s", adm4)

        time.sleep(sleep_seconds) # sleep between requests to avoid hitting rate limits

    if not all_frames:
        logger.warning("No forecast data fetched for any region.")
        return pd.DataFrame()

    raw_df = pd.concat(all_frames, ignore_index=True)

    # perform aligning and interpolation to the common grid
    aligned_df = align_all_forecasts_to_common_grid(raw_df)

    logger.info("Combined aligned forecast rows: %s", len(aligned_df))
    return aligned_df

# calculate average value of relevant parameters for each city for plotting
def build_city_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df
        .groupby(["local_datetime", "kota_kabupaten"], as_index=False) # group by cities' name and time -> average value each time each city
        .agg( # perform aggregate function (mean) to each parameter for each city
            avg_temperature_c=("temperature_c", "mean"),
            avg_humidity_ptg=("humidity_ptg", "mean"),
            avg_heat_index_c=("heat_index_c", "mean"),
        )
    )
    return summary

# this function ensures that the SQLite table used to store the forecasts exists before writing data into it
# If the table does not exist, it creates it. If it already exists, nothing happens.
def create_table_if_needed(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {WEATHER_TABLE} (
            adm4 TEXT,
            desa_kelurahan TEXT,
            kecamatan TEXT,
            kota_kabupaten TEXT,
            provinsi TEXT,
            latitude REAL,
            longitude REAL,
            timezone TEXT,
            local_datetime TEXT,
            temperature_c REAL,
            humidity_ptg REAL,
            heat_index_c REAL,
            risk_level TEXT,
            weather_desc TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY("local_datetime","adm4")
        )
        """
    )
    conn.commit()

def save_to_sqlite(df: pd.DataFrame, db_path: Path) -> None:
    """
    Delete old rows for the adm4 codes being refreshed, then append fresh rows.
    """
    if df.empty:
        logger.warning("DataFrame is empty. Nothing to save.")
        return

    conn = sqlite3.connect(db_path)

    try:
        create_table_if_needed(conn)

        df_to_save = df.copy()

        df_to_save["local_datetime"] = df_to_save["local_datetime"].astype(str) # convert datetime to string for SQLite, because SQLite does not have a native datetime type
        df_to_save["fetched_at"] = df_to_save["fetched_at"].astype(str)

        df_to_save.to_sql(WEATHER_TABLE, conn, if_exists="replace", index=False) # IMPORTANT! this will replace all existing rows so no past data recorded

        # create SQL indexes for faster querying
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_weather_time
            ON ward_weather_table(local_datetime);
            """)
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_weather_region_time
            ON ward_weather_table(adm4, local_datetime);
            """)

        summary_df = build_city_summary_table(df)
        summary_df.to_sql(
            CITY_SUMMARY_TABLE,
            conn,
            if_exists="replace",
            index=False,
        )
        # build indexing for faster query
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_city_summary_time
            ON {CITY_SUMMARY_TABLE} (local_datetime);
            """)

        conn.commit()

    finally:
        conn.close()

def main():
    setup_logging()
    print("")
    logger.info("=== BMKG refresh job started ===")
    print("")

    try:
        ref_df = load_reference_csv(REFERENCE_FILE)
        logger.info("Loaded %s reference locations from %s", len(ref_df), REFERENCE_FILE)

        df = fetch_all_jakarta_forecasts(ref_df, sleep_seconds=1.01, region_list=None)
        # set region_list to a list of adm4 codes desired, otherwise set to None to fetch all regions in the reference file

        if df.empty:
            print("")
            logger.warning("No forecast data fetched. Nothing saved.")
            print("")
            return 1

        df = add_fetched_at(df)
        save_to_sqlite(df, DB_PATH)

        print("")
        logger.info("=== BMKG refresh job completed successfully ===")
        print("")

        return 0
    
    except Exception:
        print("")
        logger.exception("=== BMKG refresh job failed ===")
        print("")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
