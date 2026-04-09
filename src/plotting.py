#!/usr/bin/env python3
'''
Helpers for plotting functions.
Some of the functions include SQL query for faster loading logic.
'''

import plotly.graph_objects as go
import pandas as pd
import numpy as np

from .helpers import format_timestamp, short_city_name, run_query
from .constant import RISK_CODE_MAP, RISK_ORDER, RISK_COLOR_MAP, WEATHER_TABLE


def classify_city_risk(heat_index_c: float) -> str:
    if pd.isna(heat_index_c):
        return "No Data"
    if heat_index_c < 26.7:
        return "Lower Risk"
    if heat_index_c < 32.2:
        return "Caution"
    if heat_index_c < 39.4:
        return "Extreme Caution"
    if heat_index_c < 51.1:
        return "Danger"
    return "Extreme Danger"



# function to get the most common weather description for a city; assumed to represent average
def most_common_weather(series: pd.Series) -> str:
    values = series.dropna().astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return ""
    mode = values.mode()
    if mode.empty:
        return ""
    return str(mode.iloc[0])


# function to build the choropleth map figure
def build_map_figure(
    boundary_geojson: dict,
    locations: list[str],
    colormap: dict,
) -> go.Figure():

    colorscale = make_discrete_colorscale()

    fig = go.Figure()

    # fig.add_trace(
    #     go.Choropleth(
    #         geojson=boundary_geojson, # boundary polygon in JSON dict
    #         locations=locations, # location index to polygon in string
    #         z=colormap["z"], # color
    #         customdata=colormap["customdata"], # other data
    #         featureidkey="properties.city_name",
    #         zmin=0,
    #         zmax=len(RISK_ORDER) - 1,
    #         colorscale=colorscale,
    #         showscale=False,
    #         marker_line_color="rgba(70,70,70,0.8)",
    #         marker_line_width=0.8,
    #         hovertemplate=(
    #             "&nbsp;<b>%{customdata[0]}</b>&nbsp;<br>"
    #             "&nbsp;%{customdata[1]}&nbsp;<br>"
    #             "&nbsp;Avg HI %{customdata[2]:.1f} °C - %{customdata[3]}&nbsp;<br>"
    #             "&nbsp;Avg Temp %{customdata[5]:.1f} °C - Avg Humidity %{customdata[6]:.0f}%&nbsp;<br>"
    #             "&nbsp;%{customdata[4]}&nbsp;"
    #             "<extra></extra>"
    #         )
    #     )

    fig.add_trace(
        go.Choroplethmap(
            geojson=boundary_geojson,
            locations=locations,
            z=colormap["z"],
            customdata=colormap["customdata"],
            featureidkey="properties.adm4",
            zmin=0,
            zmax=len(RISK_ORDER) - 1,
            colorscale=colorscale,
            showscale=False,
            # opacity=0.7,
            marker_line_color="rgba(70,70,70,0.85)",
            marker_line_width=1.0,
            hovertemplate=(
                "&nbsp;<b>%{customdata[0]}, %{customdata[1]}</b>&nbsp;<br>"
                "&nbsp;%{customdata[2]|%b %d %H:%M}&nbsp;<br>"
                f"&nbsp;{'HI'} %{{customdata[3]:.1f}} °C - %{{customdata[4]}}&nbsp;<br>"
                "&nbsp;%{customdata[5]}&nbsp;"
                "<extra></extra>"
            ),
        )
    )

    fig.update_geos(
        visible=False,
        bgcolor="rgba(0,0,0,0)",
        center={"lon": 106.8456, "lat": -6.2088}, # jakarta coordinate
        fitbounds="locations",
        projection=dict(scale=5, type="bonne")
    )

    # fig.update_layout(
    #     height=None,
    #     autosize=True,
    #     margin=dict(l=0, r=0, t=0, b=0, autoexpand=True),
    #     paper_bgcolor="rgba(0,0,0,0)",
    #     plot_bgcolor="rgba(0,0,0,0)",
    #     showlegend=False,
    #     hoverlabel=dict(
    #         bgcolor="rgba(203, 210, 200, 0.4)",
    #         font_size=13,
    #         font_family="Arial",
    #         font_color="#222",
    #         bordercolor="rgba(0,0,0,0.9)",
    #         align="left",
    #         namelength=-1,
    #     )
    # )
    fig.update_traces(marker_opacity=0.55, selector=dict(type='choroplethmap')) # set opacity
    fig.update_layout(
        map=dict(
            style="carto-positron",
            center={"lon": 106.8456, "lat": -6.2088},
            zoom=10.5,
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(
            bgcolor="rgba(203, 210, 200, 0.85)",
            font_size=13,
            font_family="Arial",
            font_color="#222",
        ),
    )

    return fig


def make_discrete_colorscale():
    """
      0 No Data
      1 Lower Risk
      2 Caution
      3 Extreme Caution
      4 Danger
      5 Extreme Danger
    """
    n = len(RISK_ORDER)
    if n == 1:
        return [[0.0, RISK_COLOR_MAP[RISK_ORDER[0]]], [1.0, RISK_COLOR_MAP[RISK_ORDER[0]]]]

    scale = []
    for i, label in enumerate(RISK_ORDER):
        start = i / (n - 1)
        end = i / (n - 1)
        color = RISK_COLOR_MAP[label]
        scale.append([start, color])
        scale.append([end, color])
    return scale



# # function to create the colormap
# # the choropleth figure itself will be built in the app.py callback function for faster loading logic
# def create_dynamic_colormap(
#     selected_time: pd.Timestamp,
#     boundary_geojson: dict,
#     conn,
# ):
#     selected_time = pd.to_datetime(selected_time).strftime("%Y-%m-%d %H:%M:%S")

#     # query = f"""
#     #     SELECT
#     #         COALESCE(kota_kabupaten, '') AS kota_kabupaten,
#     #         local_datetime,
#     #         temperature_c,
#     #         humidity_ptg,
#     #         heat_index_c,
#     #         COALESCE(weather_desc, '') AS weather_desc
#     #     FROM {WEATHER_TABLE}
#     #     WHERE local_datetime = '{selected_time}'
#     #     ORDER BY kota_kabupaten
#     # """

#     weather_df = run_query(query, conn)
#     boundary_index = pd.DataFrame(
#         {
#             "city_name": [
#                 short_city_name(feature.get("properties", {}).get("city_name", ""))
#                 for feature in boundary_geojson.get("features", [])
#             ]
#         }
#     )
#     boundary_index = (
#         boundary_index
#         .dropna(subset=["city_name"])
#         .query("city_name != ''")
#         .drop_duplicates(subset=["city_name"])
#         .sort_values("city_name")
#         .reset_index(drop=True)
#     )

#     if weather_df.empty:
#         weather_df = pd.DataFrame(
#             columns=[
#                 "city_name",
#                 "local_datetime",
#                 "avg_temperature_c",
#                 "avg_humidity_ptg",
#                 "avg_heat_index_c",
#                 "weather_desc",
#                 "risk_level",
#             ]
#         )
#     else:
#         weather_df["city_name"] = weather_df["kota_kabupaten"].apply(short_city_name)
#         weather_df = (
#             weather_df
#             .groupby("city_name", as_index=False)
#             .agg(
#                 local_datetime=("local_datetime", "first"),
#                 avg_temperature_c=("temperature_c", "mean"),
#                 avg_humidity_ptg=("humidity_ptg", "mean"),
#                 avg_heat_index_c=("heat_index_c", "mean"),
#                 weather_desc=("weather_desc", most_common_weather),
#             )
#         )
#         weather_df["risk_level"] = weather_df["avg_heat_index_c"].apply(classify_city_risk)

#     merged = boundary_index.merge(weather_df, on="city_name", how="left")
#     merged["risk_level"] = merged["risk_level"].fillna("No Data")
#     merged["weather_desc"] = merged["weather_desc"].fillna("")
#     merged["local_datetime"] = merged["local_datetime"].apply(format_timestamp)

#     z = (
#         merged["risk_level"]
#         .map(RISK_CODE_MAP)
#         .fillna(RISK_CODE_MAP["No Data"])
#         .astype(float)
#         .to_numpy()
#     )

#     customdata = np.column_stack([
#             merged["city_name"].astype(str).to_numpy(),
#             merged["local_datetime"].astype(str).to_numpy(),
#             merged["avg_heat_index_c"].to_numpy(dtype=object),
#             merged["risk_level"].astype(str).to_numpy(),
#             merged["weather_desc"].astype(str).to_numpy(),
#             merged["avg_temperature_c"].to_numpy(dtype=object),
#             merged["avg_humidity_ptg"].to_numpy(dtype=object),
#             merged["city_name"].astype(str).to_numpy(),
#         ])

#     return {
#         "z": z,
#         "customdata": customdata,
#         "locations": merged["city_name"].astype(str).tolist(),
#     }

def create_dynamic_colormap(
    selected_time: pd.Timestamp,
    conn,
):
    selected_time = pd.to_datetime(selected_time).strftime("%Y-%m-%d %H:%M:%S")

    query = f"""
        SELECT
            b.adm4 AS adm4,
            COALESCE(w.desa_kelurahan, '') AS desa_kelurahan,
            COALESCE(w.kecamatan, '') AS kecamatan,
            w.local_datetime AS local_datetime,
            w.heat_index_c AS heat_index_c,
            COALESCE(w.risk_level, 'No Data') AS risk_level,
            COALESCE(w.weather_desc, '') AS weather_desc
        FROM map_boundary_index b
        LEFT JOIN {WEATHER_TABLE} w
            ON b.adm4 = w.adm4
           AND w.local_datetime = '{selected_time}'
        ORDER BY b.adm4
    """

    # print(selected_time)

    merged = run_query(query, conn) # merging between weather and boundary data is done in SQL

    merged["local_datetime"] = merged["local_datetime"].apply(format_timestamp)

    z = (
        merged["risk_level"]
        .map(RISK_CODE_MAP)
        .fillna(RISK_CODE_MAP["No Data"])
        .astype(float)
        .to_numpy()
    )

    customdata = np.column_stack(
        [
            merged["desa_kelurahan"].astype(str).to_numpy(),
            merged["kecamatan"].astype(str).to_numpy(),
            merged["local_datetime"].astype(str).to_numpy(),
            merged["heat_index_c"].to_numpy(dtype=object),
            merged["risk_level"].astype(str).to_numpy(),
            merged["weather_desc"].astype(str).to_numpy(),
            merged["adm4"].astype(str).to_numpy(),
        ]
    )

    return {
        "z": z,
        "customdata": customdata,
    }



# function to build the heat index time plot in Ward Info
def build_heat_index_plot(
    df: pd.DataFrame,
) -> go.Figure:

    df = df.copy()
    df["local_datetime"] = pd.to_datetime(df["local_datetime"], errors="coerce")
    df = df.sort_values("local_datetime").head(6).reset_index(drop=True)

    fig = go.Figure()

    x_values = df["local_datetime"].tolist()
    y_hi = df["heat_index_c"].tolist()
    y_temp = df["temperature_c"].tolist()
    y_humidity = df["humidity_ptg"].tolist()

    y_min = min(y_hi + y_temp) # shared y-axis range for comparability
    y_max = max(y_hi + y_temp) # shared y-axis range for comparability
    if y_min == y_max:
        y_min -= 1
        y_max += 1

    span = y_max - y_min
    pad = max(1.0, span * 0.18)
    label_top = y_max + (pad * 2.3)
    label_mid = y_max + (pad * 1.45)
    label_bottom = y_min - (pad * 1.5)

    fig.add_trace( # heat index curve
        go.Scatter(
            x=x_values,
            y=y_hi,
            mode="lines+markers",
            line=dict(color="#eb8531", width=3.5, shape="spline", smoothing=0.9),
            marker=dict(size=11, color="#fffdf7", line=dict(width=2.2, color="#f1dd95")),
            hovertemplate="<b>%{x|%H:%M}</b><br>Heat Index: %{y:.1f} °C<extra></extra>",
            showlegend=False,
        )
    )
    fig.add_trace( # temperature curve
        go.Scatter(
            x=x_values,
            y=y_temp,
            mode="lines+markers",
            line=dict(color="#31a2eb", width=3.5, shape="spline", smoothing=0.9),
            marker=dict(size=11, color="#fffdf7", line=dict(width=2.2, color="#95c1f1")),
            hovertemplate="<b>%{x|%H:%M}</b><br>Temperature: %{y:.1f} °C<extra></extra>",
            showlegend=False,
        )
    )

    annotations = []
    for x_val, temp_val, hi_val, humidity_val in zip(x_values, y_temp, y_hi, y_humidity):
        annotations.extend(
            [   

                # timestamp label
                dict(
                    x=x_val,
                    y=label_bottom,
                    text=pd.Timestamp(x_val).strftime("%d %b<br>%H:%M"),
                    showarrow=False,
                    font=dict(size=16, color="#35332f", family="DM Sans, sans-serif"),
                    xanchor="center",
                ),

                # temperature label
                dict(
                    x=x_val,
                    y=label_mid,
                    text=f"{temp_val:.0f}°C",
                    showarrow=False,
                    font=dict(size=31, color="#35332f", family="DM Serif Display, serif"),
                    xanchor="center",
                ),

                # heat index label
                dict(
                    x=x_val,
                    y=label_mid - (pad * 0.78),
                    text=f"HI {hi_val:.0f}°C",
                    showarrow=False,
                    font=dict(size=14, color="#35332f", family="DM Sans, sans-serif"),
                    xanchor="center",
                ),

                # humidity label
                dict(
                    x=x_val,
                    y=label_top,
                    text=f"Humidity {humidity_val:.0f}%",
                    showarrow=False,
                    font=dict(size=14, color="#35332f", family="DM Sans, sans-serif"),
                    xanchor="center",
                ),
            ]
        )

    fig.update_layout(
        height=None,
        margin=dict(l=10, r=10, t=18, b=16),
        paper_bgcolor="rgba(0,0,0,0)", # transparent background
        plot_bgcolor="rgba(0,0,0,0)", # transparent background
        annotations=annotations,
        xaxis=dict(
            title=None,
            showgrid=False,
            zeroline=False,
            showline=False,
            showticklabels=False,
            fixedrange=True,
        ),
        yaxis=dict(
            title=None,
            range=[label_bottom - (pad * 0.8), label_top + (pad * 0.6)],
            showgrid=False,
            zeroline=False,
            showline=False,
            showticklabels=False,
            fixedrange=True,
        ),
        hoverlabel=dict(
            bgcolor="rgba(55, 72, 88, 0.96)",
            font_size=13,
            font_family="DM Sans, sans-serif",
            font_color="#ffffff",
            bordercolor="rgba(255,255,255,0.12)",
            align="left",
            namelength=-1,
        ),
    )

    return fig
