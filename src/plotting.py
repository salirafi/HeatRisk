#!/usr/bin/env python3
'''
Helpers for plotting functions.
Some of the functions include SQL query for faster loading logic.
'''

import plotly.graph_objects as go
import pandas as pd

from .helpers import format_timestamp, run_query
from .constant import RISK_CODE_MAP, WEATHER_TABLE



def create_dynamic_colormap(
    selected_time: pd.Timestamp,
    boundary_index: pd.DataFrame,
    conn,
):
    selected_time = pd.to_datetime(selected_time).strftime("%Y-%m-%d %H:%M:%S")

    query = f"""
        SELECT
            adm4,
            COALESCE(desa_kelurahan, '') AS desa_kelurahan,
            COALESCE(kecamatan, '') AS kecamatan,
            local_datetime,
            heat_index_c,
            COALESCE(risk_level, 'No Data') AS risk_level,
            COALESCE(weather_desc, '') AS weather_desc
        FROM {WEATHER_TABLE}
        WHERE local_datetime = '{selected_time}'
        ORDER BY adm4
    """

    # print(selected_time)

    weather_df = run_query(query, conn)

    if weather_df.empty:
        weather_df = pd.DataFrame(
            columns=[
                "adm4",
                "desa_kelurahan",
                "kecamatan",
                "local_datetime",
                "heat_index_c",
                "risk_level",
                "weather_desc",
            ]
        )
    else:
        weather_df["adm4"] = weather_df["adm4"].astype(str).str.strip()

    merged = boundary_index.merge(weather_df, on="adm4", how="left") # not using LEFT JOIN in SQL (slow cloud connection)

    merged["desa_kelurahan"] = merged["desa_kelurahan"].fillna("")
    merged["kecamatan"] = merged["kecamatan"].fillna("")
    merged["risk_level"] = merged["risk_level"].fillna("No Data")
    merged["weather_desc"] = merged["weather_desc"].fillna("")

    merged["local_datetime"] = merged["local_datetime"].apply(format_timestamp)

    z = (
        merged["risk_level"]
        .map(RISK_CODE_MAP)
        .fillna(RISK_CODE_MAP["No Data"])
        .astype(float)
        .tolist()
    )

    customdata = [
        [
            str(row["desa_kelurahan"]),
            str(row["kecamatan"]),
            str(row["local_datetime"]),
            row["heat_index_c"],
            str(row["risk_level"]),
            str(row["weather_desc"]),
            str(row["adm4"]),
        ]
        for _, row in merged.iterrows() # iterrows can be slow but df is small
    ]

    return {
        "z": z,
        "customdata": customdata,
    }

# like choropleth map, separate the building of base figure from dynamic data
def build_base_heat_index_figure() -> go.Figure:
    fig = go.Figure()

    fig.add_trace( # heat index curve
        go.Scatter(
            x=[],
            y=[],
            mode="lines+markers",
            line=dict(color="#eb8531", width=3.5, shape="spline", smoothing=0.9),
            marker=dict(size=11, color="#fffdf7", line=dict(width=2.2, color="#f1dd95")),
            name="Heat Index",
            customdata=[],
            hovertemplate="<b>%{customdata}</b><br>Heat Index: %{y:.1f} °C<extra></extra>",
            showlegend=True,
        )
    )
    fig.add_trace( # temperature curve
        go.Scatter(
            x=[],
            y=[],
            mode="lines+markers",
            line=dict(color="#31a2eb", width=3.5, shape="spline", smoothing=0.9),
            marker=dict(size=11, color="#fffdf7", line=dict(width=2.2, color="#95c1f1")),
            name="Temperature",
            customdata=[],
            hovertemplate="<b>%{customdata}</b><br>Temperature: %{y:.1f} °C<extra></extra>",
            showlegend=True,
        )
    )

    fig.update_layout(
        height=None,
        margin=dict(l=10, r=10, t=18, b=16),
        paper_bgcolor="rgba(0,0,0,0)", # transparent background
        plot_bgcolor="rgba(0,0,0,0)",
        annotations=[],
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            bgcolor="rgba(255,253,247,0.82)",
            bordercolor="rgba(53, 51, 47, 0.10)",
            borderwidth=1,
            font=dict(size=12, color="#35332f", family="DM Sans, sans-serif"),
        ),
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
            range=[0, 1],
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

# curve plot
def build_heat_index_plot_state(
    df: pd.DataFrame,
) -> dict:

    df = df.copy()
    df["local_datetime"] = pd.to_datetime(df["local_datetime"], errors="coerce")
    df = df.sort_values("local_datetime").reset_index(drop=True)

    x_values = df["local_datetime"].tolist() # timestamp for x-axis
    hover_times = [
        pd.Timestamp(x_val).strftime("%H:%M") if not pd.isna(x_val) else "—"
        for x_val in x_values
    ]
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

    return {
        "x_values": x_values,
        "hover_times": hover_times,
        "y_hi": y_hi,
        "y_temp": y_temp,
        "annotations": annotations,
        "yaxis_range": [label_bottom - (pad * 0.8), label_top + (pad * 0.6)],
    }
