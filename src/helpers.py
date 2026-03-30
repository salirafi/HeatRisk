#!/usr/bin/env python3
'''
Source code for other helpers functions.
'''

import sqlite3
import pandas as pd
import json
from html import escape

from .constant import DB_PATH, BOUNDARY_GEOJSON_PATH, WEATHER_TABLE

def guide_button_id(level: str) -> str:
    return {
        "Lower Risk": "guide_lower_risk",
        "Caution": "guide_caution",
        "Extreme Caution": "guide_extreme_caution",
        "Danger": "guide_danger",
        "Extreme Danger": "guide_extreme_danger",
    }[level]

def risk_badge(level: str) -> str:
    if level == "Extreme Danger":
        return "🚨 Extreme Danger"
    if level == "Danger":
        return "🔴 Danger"
    if level == "Extreme Caution":
        return "🟠 Extreme Caution"
    if level == "Caution":
        return "🟡 Caution"
    if level == "Lower Risk":
        return "🟢 Lower Risk"
    return "⚪ No Data"

# formatting pandas Timestamp to cleaner format
def format_timestamp(ts) -> str:
    if ts is None or pd.isna(ts):
        return ""
    return pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M")

def short_city_name(name: str) -> str:
    if pd.isna(name):
        return ""
    name = str(name).strip()
    return name.replace("Kota Adm. ", "")

# HTML for current-weather metric cards
def metric_card_html(label: str, value: str, extra_class: str = "") -> str:
    return f"""
    <div class="metric-card {extra_class}">
        <div class="metric-label">{escape(label)}</div>
        <div class="metric-value">{value}</div>
    </div>
    """
def hex_to_rgba_css(hex_color: str, alpha: float = 0.05) -> str:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return f"rgba(220,220,220,{alpha})"

    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

def run_query(query: str, conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(query, conn)

# function to get name of all tables in sqlite database
def get_table_names(conn) -> list[str]:
    tables = run_query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", conn)
    return tables["name"].tolist()

# function to load boundary data from boundary table
def load_boundary_data() -> tuple[pd.DataFrame, dict]:

    with open(BOUNDARY_GEOJSON_PATH, "r", encoding="utf-8") as f:
        geojson = json.load(f) # becomes dict

    # features = geojson.get("features", [])
    # boundary_index = pd.DataFrame(
    #     {
    #         "adm4": [
    #             str(feature.get("properties", {}).get("adm4", "")).strip()
    #             for feature in features
    #         ]
    #     }
    # )

    return geojson

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

# selecting rows with the filtered-region and (current) time
def current_condition(adm4: str, current_time: pd.Timestamp, conn) -> pd.DataFrame:
    query = f"""
        SELECT *
        FROM {WEATHER_TABLE}
        WHERE adm4 = '{adm4}'
          AND local_datetime <= '{current_time.strftime("%Y-%m-%d %H:%M:%S")}'
        ORDER BY local_datetime DESC
        LIMIT 1
    """
    df = run_query(query, conn)

    if df.empty:
        return df

    df["local_datetime"] = pd.to_datetime(df["local_datetime"], errors="coerce")
    return df

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

# showing the last time the database was updated
# this is based on the fetched_at column with the latest timestamp
def get_last_db_update():
    conn = get_conn()
    try:
        df = pd.read_sql_query(
            f"""
            SELECT MAX(fetched_at) AS fetched_at
            FROM {WEATHER_TABLE}
            WHERE fetched_at IS NOT NULL
            """,
            conn,
        )
    finally:
        conn.close()

    if df.empty:
        return "-"

    ts = pd.to_datetime(df.iloc[0]["fetched_at"], errors="coerce")
    if pd.isna(ts):
        return "-"

    return ts.strftime("%b %d, %H:%M")

# options to be displayed to the search bar
# all available wards will be listed
def make_ward_search_options(conn):
    df = pd.read_sql_query(
        f"""
        SELECT DISTINCT
            kota_kabupaten,
            kecamatan,
            desa_kelurahan
        FROM {WEATHER_TABLE}
        WHERE desa_kelurahan IS NOT NULL
        ORDER BY desa_kelurahan, kecamatan, kota_kabupaten
        """,
        conn,
    )

    return [
        {
            "label": f"{row['desa_kelurahan']}, {row['kecamatan']}, {row['kota_kabupaten']}",
            "value": row["desa_kelurahan"],
        }
        for _, row in df.iterrows()
    ]

# convert a list of timestamps into JSON-serializable strings so they can be stored in dcc.Store
def serialize_timestamps(times):
    return [pd.Timestamp(ts).isoformat() for ts in times]

# converting back into pd.Timestamp objects for computation
def deserialize_timestamps(times_data):
    if not times_data:
        return []
    return [pd.Timestamp(ts) for ts in times_data]

def get_selected_time_from_store(selected_idx, times_data):
    times = deserialize_timestamps(times_data)
    if not times:
        return None

    if selected_idx is None:
        selected_idx = 0

    selected_idx = max(0, min(int(selected_idx), len(times) - 1))
    return pd.Timestamp(times[selected_idx])

# connect to SQLite
# note that the connection is closed outside of this function
def get_conn():
    return sqlite3.connect(DB_PATH)

# create label marks for time slider so only a few timestamps are displayed
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

# ##############
# FUNCTIONS FOR DROP-DOWN SELECTION
# since the current version of the app uses search bar,
# these functions below are deprecated and collectively replaced by make_ward_search_options()
# ##############

def city_options(conn) -> list[str]: # fory city-level
    query = f"""
        SELECT DISTINCT kota_kabupaten
        FROM {WEATHER_TABLE}
        WHERE kota_kabupaten IS NOT NULL
          AND TRIM(kota_kabupaten) != ''
        ORDER BY kota_kabupaten
    """
    df = run_query(query, conn)
    if df.empty:
        return []
    return df["kota_kabupaten"].astype(str).str.strip().tolist()
def subdistrict_options(selected_city: str, conn) -> list[str]: # for subdistrict-level
    query = f"""
        SELECT DISTINCT kecamatan
        FROM {WEATHER_TABLE}
        WHERE kota_kabupaten = '{selected_city}'
          AND kecamatan IS NOT NULL
          AND TRIM(kecamatan) != ''
        ORDER BY kecamatan
    """
    df = run_query(query, conn)
    if df.empty:
        return []
    return df["kecamatan"].astype(str).str.strip().tolist()
def ward_options(selected_city: str, selected_subdistrict: str, conn) -> list[str]: # for ward-level
    query = f"""
        SELECT DISTINCT desa_kelurahan
        FROM {WEATHER_TABLE}
        WHERE kota_kabupaten = '{selected_city}'
          AND kecamatan = '{selected_subdistrict}'
          AND desa_kelurahan IS NOT NULL
          AND TRIM(kecamatan) != ''
        ORDER BY kecamatan
    """
    df = run_query(query, conn)
    if df.empty:
        return []
    return df["desa_kelurahan"].astype(str).str.strip().tolist()
    
# function to get the region code for the selected region for filtering the database to the selected reigion
def ward_final_selection(selected_city: str, selected_subdistrict: str, selected_ward: str, conn) -> str | None:
    query = f"""
        SELECT adm4
        FROM {WEATHER_TABLE}
        WHERE kota_kabupaten = '{selected_city}'
          AND kecamatan = '{selected_subdistrict}'
          AND desa_kelurahan = '{selected_ward}'
        ORDER BY local_datetime
        LIMIT 1
    """
    df = run_query(query, conn)
    if df.empty:
        return None
    value = df.iloc[0]["adm4"] # get the code
    return str(value).strip()


