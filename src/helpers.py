#!/usr/bin/env python3
'''
Source code for other helpers functions.
'''

import pandas as pd
import json
import re
import gzip

from .constant import (
    APP_RUNTIME_METADATA_TABLE,
    BOUNDARY_GEOJSON_PATH,
    BOUNDARY_GEOJSON_GZ_PATH,
    WEATHER_TABLE,
)
from .db import get_conn, get_sql_param_placeholder
def format_timestamp(ts) -> str:
    if ts is None or pd.isna(ts):
        return ""
    return pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M")


def run_query(query: str, conn) -> pd.DataFrame:
    return pd.read_sql_query(query, conn)


def create_runtime_metadata_table_if_needed(conn) -> None:
    conn.cursor().execute(
        f"""
        CREATE TABLE IF NOT EXISTS {APP_RUNTIME_METADATA_TABLE} (
            metadata_key VARCHAR(64) NOT NULL,
            last_db_update DATETIME NULL,
            forecast_times_json LONGTEXT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (metadata_key)
        )
        """
    )
    conn.commit()


def load_runtime_metadata() -> dict:
    conn = get_conn()
    try:
        create_runtime_metadata_table_if_needed(conn)
        placeholder = get_sql_param_placeholder(conn)
        df = pd.read_sql_query(
            f"""
            SELECT
                last_db_update,
                forecast_times_json
            FROM {APP_RUNTIME_METADATA_TABLE}
            WHERE metadata_key = {placeholder}
            LIMIT 1
            """,
            conn,
            params=["runtime"],
        )
    finally:
        conn.close()

    if df.empty:
        return {}

    row = df.iloc[0]
    forecast_times = []
    raw_forecast_times = row.get("forecast_times_json")
    if raw_forecast_times:
        try:
            parsed_times = json.loads(raw_forecast_times)
            if isinstance(parsed_times, list):
                forecast_times = parsed_times
        except json.JSONDecodeError:
            forecast_times = []

    last_db_update = row.get("last_db_update")
    if last_db_update is not None and not pd.isna(last_db_update):
        last_db_update = pd.Timestamp(last_db_update).isoformat()
    else:
        last_db_update = None

    return {
        "last_db_update": last_db_update,
        "forecast_times": forecast_times,
    }


def write_runtime_metadata(payload: dict) -> None:
    conn = get_conn()
    try:
        create_runtime_metadata_table_if_needed(conn)
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"""
                REPLACE INTO {APP_RUNTIME_METADATA_TABLE} (
                    metadata_key,
                    last_db_update,
                    forecast_times_json,
                    updated_at
                )
                VALUES (%s, %s, %s, NOW())
                """,
                (
                    "runtime",
                    payload.get("last_db_update"),
                    json.dumps(payload.get("forecast_times", []), ensure_ascii=False, separators=(",", ":")),
                ),
            )
            conn.commit()
        finally:
            cursor.close()
    finally:
        conn.close()

# function to load boundary data from exported GeoJSON
def load_boundary_data() -> dict:
    if BOUNDARY_GEOJSON_GZ_PATH.exists():
        with gzip.open(BOUNDARY_GEOJSON_GZ_PATH, "rt", encoding="utf-8") as f:
            geojson = json.load(f) # becomes dict
    else:
        with open(BOUNDARY_GEOJSON_PATH, "r", encoding="utf-8") as f:
            geojson = json.load(f) # becomes dict

    return geojson

def load_map_boundary_index_from_geojson(boundary_geojson: dict) -> pd.DataFrame:
    rows = []

    for feature in boundary_geojson.get("features", []):
        adm4 = str(feature.get("properties", {}).get("adm4", "")).strip()
        if adm4:
            rows.append({"adm4": adm4})

    if not rows:
        return pd.DataFrame(columns=["adm4"])

    df = pd.DataFrame(rows)
    return (
        df
        .drop_duplicates(subset=["adm4"])
        .sort_values("adm4")
        .reset_index(drop=True)
    )

# get unique timestamp values in weather data
def available_timestamps(start_time: pd.Timestamp, end_time: pd.Timestamp, conn) -> list[pd.Timestamp]:
    query = f"""
        SELECT DISTINCT local_datetime
        FROM {WEATHER_TABLE}
        WHERE local_datetime >= '{start_time}'
          AND local_datetime <= '{end_time}'
        ORDER BY local_datetime
    """
    df = run_query(query, conn)

    if df.empty:
        return []

    return pd.to_datetime(df["local_datetime"]).tolist() # list of pd.Timestamp sorted

# function to query future weather data relative to current time
def future_forecast(adm4: str, current_time: pd.Timestamp, end_time: pd.Timestamp, conn) -> pd.DataFrame:
    query = f"""
        SELECT *
        FROM {WEATHER_TABLE}
        WHERE adm4 = '{adm4}'
          AND local_datetime BETWEEN '{current_time.strftime("%Y-%m-%d %H:%M:%S")}'
                                AND '{end_time.strftime("%Y-%m-%d %H:%M:%S")}'
        ORDER BY local_datetime
    """
    df = run_query(query, conn)

    if df.empty:
        return df

    df["local_datetime"] = pd.to_datetime(df["local_datetime"], errors="coerce")
    return df


def future_forecast_for_store(adm4: str, current_time: pd.Timestamp, end_time: pd.Timestamp, conn) -> list[dict]:
    df = future_forecast(adm4, current_time, end_time, conn)

    if df.empty:
        return []

    records = []
    for row in df.to_dict(orient="records"):
        record = dict(row)
        if record.get("local_datetime") is not None and not pd.isna(record["local_datetime"]):
            record["local_datetime"] = pd.Timestamp(record["local_datetime"]).isoformat()
        records.append(record)

    return records
def normalize_search_text(text: str) -> str:
    if text is None:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", "", str(text).lower())
    return normalized.strip()


def search_ward_options(query_text: str, conn, limit: int = 12) -> list[dict]:
    normalized_query = normalize_search_text(query_text)
    if not normalized_query:
        return []

    df = pd.read_sql_query(
        f"""
        SELECT DISTINCT
            adm4,
            kota_kabupaten,
            kecamatan,
            desa_kelurahan
        FROM {WEATHER_TABLE}
        WHERE desa_kelurahan IS NOT NULL
          AND adm4 IS NOT NULL
        ORDER BY desa_kelurahan, kecamatan, kota_kabupaten, adm4
        """,
        conn,
    )

    if df.empty:
        return []

    df["label"] = (
        df["desa_kelurahan"].astype(str)
        + ", "
        + df["kecamatan"].astype(str)
        + ", "
        + df["kota_kabupaten"].astype(str)
    )
    df["normalized_label"] = df["label"].apply(normalize_search_text)

    contains_mask = df["normalized_label"].str.contains(normalized_query, regex=False)
    starts_mask = df["normalized_label"].str.startswith(normalized_query)

    ranked = df[contains_mask].copy()
    if ranked.empty:
        return []

    ranked["starts_with_query"] = starts_mask[contains_mask].astype(int)
    ranked["label_length"] = ranked["normalized_label"].str.len()
    ranked = ranked.sort_values(
        ["starts_with_query", "label_length", "label"],
        ascending=[False, True, True],
    ).head(limit)

    return [
        {
            "label": row["label"],
            "value": row["adm4"],
        }
        for _, row in ranked.iterrows()
    ]
def deserialize_timestamps(times_data):
    if not times_data:
        return []
    return [pd.Timestamp(ts) for ts in times_data]

def build_slider_marks(times):
    if not times:
        return {}
    n = len(times)
    if n <= 8: # if number of timestamps < 8, display all
        idxs = list(range(n))
    else: # else display only three
        idxs = sorted(set([0, n // 2, n - 1]))
    return {
        i: pd.Timestamp(times[i]).strftime("%b %d\n%H:%M")
        for i in idxs
    }
