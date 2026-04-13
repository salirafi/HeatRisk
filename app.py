#!/usr/bin/env python3
"""
Flask entrypoint for the React version of the heat risk app.
"""

from __future__ import annotations

import json

import pandas as pd
from flask import Flask, jsonify, render_template, request

from src.constant import (
    HEAT_RISK_GUIDE,
    RISK_ABBR,
    RISK_COLOR_MAP,
    RISK_LABEL_MAP,
    WEATHER_ICON_MAP,
)
from src.db import get_conn, get_current_jakarta_time
from src.helpers import (
    build_slider_marks,
    deserialize_timestamps,
    future_forecast_for_store,
    load_boundary_data,
    load_map_boundary_index_from_geojson,
    load_runtime_metadata,
    search_ward_options,
)
from src.plotting import (
    build_base_heat_index_figure,
    build_heat_index_plot_state,
    create_dynamic_colormap,
)

app = Flask(
    __name__,
    static_folder="assets",
    static_url_path="/assets",
    template_folder="templates",
)

_boundary_json = None # cache the boundary geojson since it's static
_map_boundary_index_df = None # cache the map boundary index dataframe since it's static
_base_heat_index_figure = None # cache the base heat index figure since it's static


def get_boundary_json():
    global _boundary_json

    if _boundary_json is None:
        _boundary_json = load_boundary_data()
    return _boundary_json
def get_map_boundary_index_df():
    global _map_boundary_index_df

    if _map_boundary_index_df is None:
        _map_boundary_index_df = load_map_boundary_index_from_geojson(get_boundary_json())
    return _map_boundary_index_df

def get_base_heat_index_figure():
    global _base_heat_index_figure

    if _base_heat_index_figure is None:
        _base_heat_index_figure = build_base_heat_index_figure()
    return _base_heat_index_figure

def get_default_query_window():
    current_time = get_current_jakarta_time()
    return {
        "start_time": current_time,
        "end_time": current_time + pd.Timedelta(days=2.0), # default to 2-day window for both ward forecast and map display
    }


def load_forecast_times(runtime_metadata=None): # allow passing runtime_metadata avoid redundant file reads when already loaded in cron_refresh handler
    from src.helpers import available_timestamps

    metadata = runtime_metadata if runtime_metadata is not None else load_runtime_metadata()
    cached_times = metadata.get("forecast_times")
    if cached_times:
        return deserialize_timestamps(cached_times)

    window = get_default_query_window()

    # margin of 3 hours
    start_time = pd.to_datetime(window["start_time"]) - pd.Timedelta(hours=3.0)
    end_time = pd.to_datetime(window["end_time"]) + pd.Timedelta(hours=3.0)

    conn = get_conn()
    try:
        return available_timestamps(start_time, end_time, conn)
    finally:
        conn.close()

def get_nearest_current_time(times):
    if not times:
        return None

    times_series = pd.Series(times)
    current_time = get_current_jakarta_time()
    nearest_idx = (times_series - current_time).abs().idxmin()
    return pd.Timestamp(times_series.loc[nearest_idx])


def format_display_time(ts):
    if ts is None or pd.isna(ts):
        return "—"
    return pd.Timestamp(ts).strftime("%b %d, %H:%M")


def sanitize_number(value):
    if value is None or pd.isna(value):
        return None
    return float(value)

# convert a Plotly figure to a JSON-serializable dict
def figure_to_json(figure):
    import plotly.io as pio
    return json.loads(pio.to_json(figure))


def build_timeline_figure(forecast_records):
    if not forecast_records:
        return figure_to_json(get_base_heat_index_figure())

    df = pd.DataFrame(forecast_records)
    if df.empty:
        return figure_to_json(get_base_heat_index_figure())

    df["local_datetime"] = pd.to_datetime(df["local_datetime"], errors="coerce")
    plot_state = build_heat_index_plot_state(df=df.head(6).copy()) # limit to 6 records to avoid overcrowding the timeline
    fig = figure_to_json(get_base_heat_index_figure()) # start from the base figure and update data and layout to preserve config and styling
    fig["data"][0]["x"] = plot_state["x_values"]
    fig["data"][0]["y"] = plot_state["y_hi"]
    fig["data"][0]["customdata"] = plot_state["hover_times"]
    fig["data"][1]["x"] = plot_state["x_values"]
    fig["data"][1]["y"] = plot_state["y_temp"]
    fig["data"][1]["customdata"] = plot_state["hover_times"]
    fig["layout"]["annotations"] = plot_state["annotations"]
    fig["layout"]["yaxis"]["range"] = plot_state["yaxis_range"]
    fig["layout"]["uirevision"] = "weather-timeline"
    return fig

def build_map_feature_collection(selected_time):
    boundary_geojson = get_boundary_json()
    if selected_time is None:
        return boundary_geojson

    conn = get_conn()
    try:
        colormap = create_dynamic_colormap(
            selected_time=selected_time,
            boundary_index=get_map_boundary_index_df(),
            conn=conn,
        )
    finally:
        conn.close()

    feature_lookup = {}
    # build a lookup dict from adm4 to the relevant properties
    for row in colormap["customdata"]:
        feature_lookup[str(row[-1])] = {
            "desa_kelurahan": str(row[0]),
            "kecamatan": str(row[1]),
            "local_datetime": str(row[2]),
            "heat_index_c": row[3],
            "risk_level": str(row[4]),
            "weather_desc": str(row[5]),
            "adm4": str(row[6]),
        }

    features = []
    # identify each feature by its adm4 code
    for feature in boundary_geojson.get("features", []):
        enriched_feature = dict(feature)
        properties = dict(feature.get("properties", {}))
        adm4 = str(properties.get("adm4", "")).strip()
        properties.update(feature_lookup.get(adm4, {
            "desa_kelurahan": "",
            "kecamatan": "",
            "local_datetime": "",
            "heat_index_c": None,
            "risk_level": "No Data",
            "weather_desc": "",
            "adm4": adm4,
        }))
        properties["heat_index_c"] = sanitize_number(properties.get("heat_index_c"))
        enriched_feature["properties"] = properties
        features.append(enriched_feature)

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def load_ward_forecast(adm4, forecast_times):
    if not adm4:
        return []

    current_time_df = get_nearest_current_time(forecast_times)
    if current_time_df is None:
        return []

    end_time = get_default_query_window()["end_time"]
    conn = get_conn()
    try:
        return future_forecast_for_store(adm4, current_time_df, end_time, conn)
    finally:
        conn.close()



# build the payload for the bootstrap endpoint, 
# which includes both runtime metadata and config data needed for the frontend to initialize
def build_bootstrap_payload():
    runtime_metadata = load_runtime_metadata() # this is expected to be cached after the first load in cron_refresh
    forecast_times = load_forecast_times(runtime_metadata)

    return {
        "runtime": {
            "last_db_update_display": format_display_time(runtime_metadata.get("last_db_update")),
            "forecast_times": [pd.Timestamp(ts).isoformat() for ts in forecast_times],
            "slider_marks": build_slider_marks(forecast_times),
            "current_jakarta_time_display": format_display_time(get_current_jakarta_time()),
        },
        "config": {
            "riskColorMap": RISK_COLOR_MAP,
            "riskLabelMap": RISK_LABEL_MAP,
            "riskAbbr": RISK_ABBR,
            "weatherIconMap": WEATHER_ICON_MAP,
            "heatRiskGuide": HEAT_RISK_GUIDE,
        },
    }



@app.route("/")
@app.route("/location")
@app.route("/map")
def index():
    return render_template("index.html")


@app.get("/api/bootstrap")
def api_bootstrap():
    return jsonify(build_bootstrap_payload())


# endpoint for ward search
# this will be used by the autocomplete component in the frontend, 
# so it should return a list of options matching the query text
@app.get("/api/wards")
def api_wards():
    query_text = request.args.get("q", "").strip()
    if not query_text:
        return jsonify([])

    conn = get_conn()
    try:
        options = search_ward_options(query_text, conn) # autocomplete
    finally:
        conn.close()

    return jsonify(options)

# endpoint for forecast timeline
@app.get("/api/forecast")
def api_forecast():
    adm4 = request.args.get("adm4", "").strip()
    runtime_metadata = load_runtime_metadata()
    forecast_times = load_forecast_times(runtime_metadata)
    forecast_records = load_ward_forecast(adm4, forecast_times)
    snapshot_time = get_nearest_current_time(forecast_times) if adm4 else None

    return jsonify(
        {
            "forecast": forecast_records,
            "current_time_display": format_display_time(get_current_jakarta_time()),
            "snapshot_time_display": format_display_time(snapshot_time) if adm4 else "—",
            "timeline_figure": build_timeline_figure(forecast_records),
        }
    )

# endpoint for map data
@app.get("/api/map-data")
def api_map_data():
    runtime_metadata = load_runtime_metadata()
    forecast_times = load_forecast_times(runtime_metadata)

    selected_time_param = request.args.get("time", "").strip()
    if selected_time_param:
        selected_time = pd.to_datetime(selected_time_param, errors="coerce")
        if pd.isna(selected_time):
            selected_time = None
    else:
        selected_time = forecast_times[0] if forecast_times else None

    return jsonify(
        {
            "geojson": build_map_feature_collection(selected_time),
        }
    )


# ping for cron job to keep app running
@app.route('/ping')
def ping():
    return {'status': 'ok'}, 200



# # automatic db update with cron job
# @app.route("/fetch-latest")
# def fetch_latest():
#     from fetch.fetch_weather_data import run_refresh_job
#     try:
#         result = run_refresh_job(sleep_seconds=1.01, region_list=None)
#         status_code = 200 if result.get("status") == "success" else 500
#         return result, status_code
#     except Exception as e:
#         return {"status": "error", "message": str(e)}, 500




if __name__ == "__main__":
    app.run(debug=True)
