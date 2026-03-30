#!/usr/bin/env python3
'''
Helpers for plotting functions.
Some of the functions include SQL query for faster loading logic.
'''

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

from .helpers import format_timestamp, short_city_name, run_query
from .constant import RISK_CODE_MAP, RISK_ORDER, RISK_COLOR_MAP, CITY_COLOR_MAP, CITY_ORDER, CITY_SUMMARY_TABLE, WEATHER_TABLE

def build_map_figure(
    boundary_geojson: dict,
    locations: list[str],
    colormap: dict,
) -> go.Figure():

    colorscale = make_discrete_colorscale()

    fig = go.Figure()

    fig.add_trace(
        go.Choropleth(
            geojson=boundary_geojson, # boundary polygon in JSON dict
            locations=locations, # location index to polygon in string
            z=colormap["z"], # color
            customdata=colormap["customdata"], # other data
            featureidkey="properties.adm4",
            zmin=0,
            zmax=len(RISK_ORDER) - 1,
            colorscale=colorscale,
            showscale=False,
            marker_line_color="rgba(70,70,70,0.8)",
            marker_line_width=0.8,
            hovertemplate=(
                "&nbsp;<b>%{customdata[0]}, %{customdata[1]}</b>&nbsp;<br>"
                "&nbsp;%{customdata[2]|%b %d %H:%M}&nbsp;<br>"
                f"&nbsp;{'HI'} %{{customdata[3]:.1f}} °C - %{{customdata[4]}}&nbsp;<br>"
                "&nbsp;%{customdata[5]}&nbsp;"
                "<extra></extra>"
            )
        )
    )

    fig.update_geos(
        visible=False,
        bgcolor="rgba(0,0,0,0)",
        center={"lon": 106.8456, "lat": -6.2088}, # jakarta coordinate
        fitbounds="locations",
        # projection_scale=500,
        projection=dict(scale=5,
                        type="bonne")
    )

    fig.update_layout(
        height=None,
        autosize=True,
        margin=dict(l=0, r=0, t=0, b=0, autoexpand=True),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        # geo=dict(
        #     lonaxis_range=[106.6, 107.0],
        #     lataxis_range=[-6.4, -6.0],
        #     projection_scale=1,
        #     fitbounds=False
        # ),
        hoverlabel=dict(
            bgcolor="rgba(203, 210, 200, 0.4)",
            font_size=13,
            font_family="Arial",
            font_color="#222",
            bordercolor="rgba(0,0,0,0.9)",
            align="left",
            namelength=-1
            )
        )

    return fig

def make_discrete_colorscale():
    """
    Build a stepwise colorscale for numeric z values:
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

# function to variable that contains colormap and metadata for choropleth plotting
# this is made since the colormap is the slide-dependent component, not the boundary polygon data 
# def create_dynamic_colormap(
#     boundary_index: pd.DataFrame,
#     selected_time: pd.Timestamp, # time selected from the slider
#     conn,
# ):
    
#     selected_time = pd.to_datetime(selected_time)
    
#     query = f"""
#         SELECT adm4, desa_kelurahan, kecamatan,
#             local_datetime, heat_index_c, temperature_c, risk_level, weather_desc
#         FROM {WEATHER_TABLE}
#         WHERE local_datetime = '{selected_time}'
#         """

#     index_df = boundary_index.copy() # dataframe for region/boundary index
#     time_df = run_query(query, conn)

#     merged = index_df.merge(time_df, on="adm4", how="left") # merge based on region code adm4
#     merged["risk_level"] = merged["risk_level"].fillna("No Data") # if no data on risk_level, fill with "No Data"
#     merged["desa_kelurahan"] = merged["desa_kelurahan"].fillna("")
#     merged["kecamatan"] = merged["kecamatan"].fillna("")
#     merged["weather_desc"] = merged["weather_desc"].fillna("")
#     merged["local_datetime"] = merged["local_datetime"].apply(format_timestamp)

#     # mapping risk level in string to numerical code for faster reading by numpy
#     z = merged["risk_level"].map(RISK_CODE_MAP).fillna(RISK_CODE_MAP["No Data"]).astype(float).to_numpy()

#     # saving data for hover text on the map
#     customdata = np.column_stack(
#         [
#             merged["desa_kelurahan"].astype(str).to_numpy(),
#             merged["kecamatan"].astype(str).to_numpy(),
#             merged["local_datetime"].astype(str).to_numpy(),
#             merged["heat_index_c"].to_numpy(dtype=object),
#             merged["risk_level"].astype(str).to_numpy(),
#             merged["weather_desc"].astype(str).to_numpy(),
#         ]
#     )

#     return {
#         "z": z,
#         "customdata": customdata,
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

# function for creating map legend
def legend_html() -> str:
    items = [
        ("No Data", RISK_COLOR_MAP["No Data"]),
        ("Lower Risk", RISK_COLOR_MAP["Lower Risk"]),
        ("Caution", RISK_COLOR_MAP["Caution"]),
        ("Extreme Caution", RISK_COLOR_MAP["Extreme Caution"]),
        ("Danger", RISK_COLOR_MAP["Danger"]),
        ("Extreme Danger", RISK_COLOR_MAP["Extreme Danger"]),
    ]

    parts = []
    for label, color in items:
        parts.append(
            f"""
            <span class="legend-chip">
                <span class="legend-box" style="background:{color};"></span>
                {label}
            </span>
            """
        )
    
    return "".join(parts)

def build_city_summary_plot(
    summary_value: dict[list], # output of city_summary_at_time()
) -> go.Figure:

    fig =  make_subplots(
        rows=1,
        cols=3,
        horizontal_spacing=0.05,
        subplot_titles=(
            "Avg. Temperature (°C)",
            "Avg. Humidity (%)",
            "Avg. Heat Index (°C)",
        )
    )
    
    metrics = [
        ("avg_temperature_c", "Avg. Temperature", "°C"),
        ("avg_humidity_ptg", "Avg. Humidity", "%"),
        ("avg_heat_index_c", "Avg. Heat Index", "°C"),
    ]

    time_customdata = [[summary_value["local_datetime"]] for _ in CITY_ORDER]
    city_colors = [CITY_COLOR_MAP[city] for city in CITY_ORDER]

    # create one trace for each parameter
    for col_idx, (metric_col, metric_label, unit) in enumerate(metrics, start=1):
        fig.add_trace(
            go.Bar(
                x=CITY_ORDER,
                y=summary_value[metric_col],
                showlegend=False,
                marker_color=city_colors,
                customdata=time_customdata,
                hovertemplate=(
                                "&nbsp;<b>%{x}</b>&nbsp;<br>"
                                "&nbsp;%{customdata[0]}&nbsp;<br>"
                                f"&nbsp;{metric_label}: %{{y:.1f}} {unit}&nbsp;"
                                "<extra></extra>"
                            ),
            ),
            row=1,
            col=col_idx,
        )

    # dummy traces only for city legend
    for city in CITY_ORDER:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                name=city,
                marker=dict(size=10, color=CITY_COLOR_MAP[city]),
                showlegend=True,
                hoverinfo="skip",
                legendgroup=city,
            ),
            row=1,
            col=1,
        )

    fig.update_layout(
        height=None,
        margin=dict(l=0, r=0, t=90, b=90),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        barmode="group",

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.17,
            xanchor="left",
            x=0,
            title=None,
            traceorder="normal",  # ensures city legend order stays as added
        ),

        hoverlabel=dict(
            bgcolor="rgba(203, 210, 200, 0.4)",
            font_size=13,
            font_family="Arial",
            font_color="#222",
            bordercolor="rgba(0,0,0,0.9)",
            align="left",
            namelength=-1,
        ),
    )

    fig.update_xaxes(
        title=None,
        showgrid=False,
        zeroline=False,
        showticklabels=False,
        showline=True,
        linecolor="rgba(0,0,0,0.35)",
        linewidth=1,
    )

    for col in range(1, 4):
        fig.update_yaxes(
            row=1,
            col=col,
            title_standoff=5,
            gridcolor="rgba(0,0,0,0.08)",
            zeroline=False,
        )

    return fig

# calculate average value of relevant parameters for each city
# the summary dataframe is then converted to a dictionary of lists ordered by CITY_ORDER
def city_summary_at_time(
    selected_time: pd.Timestamp,
    conn,
) -> dict[list]:

    selected_time = pd.to_datetime(selected_time)
    metric_cols = ["avg_temperature_c", "avg_humidity_ptg", "avg_heat_index_c"]

    # query the average table
    query = f"""
        SELECT *
        FROM {CITY_SUMMARY_TABLE}
        WHERE local_datetime = '{selected_time}'
        ORDER BY kota_kabupaten
        """
    summary = run_query(query, conn)

    summary["city_short_name"] = summary["kota_kabupaten"].apply(short_city_name) # shorten city name to fit the plot neatly
    summary_map = summary.set_index("city_short_name")[metric_cols].to_dict(orient="index")

    summary_list = {} # dictionary to be filled with a list for each parameter
    for metric_col in metric_cols:
        summary_list[metric_col] = [ # for each parameter, each list is ordered by CITY_ORDER
            summary_map.get(city, {}).get(metric_col)
            for city in CITY_ORDER
        ]
    summary_list["local_datetime"] = selected_time.strftime("%b %d %H:%M")

    return summary_list

def build_heat_index_plot(
    evolution_values: dict,
) -> go.Figure:

    fig = go.Figure()

    # heat index trace
    fig.add_trace(
        go.Scatter(
            x=evolution_values["x"],
            y=evolution_values["y_hi"],
            mode="lines+markers",
            name="Heat Index",
            line=dict(color="#d62728", width=2),
            marker=dict(size=5),
            hovertemplate=(
                "Time: %{x|%b %d %H:%M}<br>"
                "Heat Index: %{y:.1f} °C<extra></extra>"
            ),
            yaxis="y",
        ) 
    )

    # temperature trace
    fig.add_trace(
        go.Scatter(
            x=evolution_values["x"],
            y=evolution_values["y_temp"],
            mode="lines+markers",
            name="Temperature",
            line=dict(color="#1f77b4", width=2, dash="dot"),
            marker=dict(size=5),
            hovertemplate=(
                "Time: %{x|%b %d %H:%M}<br>"
                "Temperature: %{y:.1f} °C<extra></extra>"
            ),
            yaxis="y2",
        ) 
    )

    annotations = []
    fig.update_layout(
        height=None,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        annotations=annotations,
        xaxis=dict(
            title=None,
            tickformat="%b %d %H:%M",
            tickangle=0,
            showgrid=True,
            gridcolor="rgba(0,0,0,0.08)",
            zeroline=False,
            visible=False,
        ),
        yaxis=dict(
            title="Heat Index (°C)",
            range=evolution_values["y_range"],
            gridcolor="rgba(0,0,0,0.08)",
            zeroline=False,
            visible=not evolution_values["is_empty"],
        ),

        yaxis2=dict(
            title="Temperature (°C)",
            range=evolution_values["y_range"], # make sure the range of the temperature is the same as heat index for non-biased comparison
            overlaying="y",
            side="right",
            showgrid=False,
            visible=not evolution_values["is_empty"],
        ),
        hoverlabel=dict(
            bgcolor="rgba(203, 210, 200, 0.4)",
            font_size=13,
            font_family="Arial",
            font_color="#222",
            bordercolor="rgba(0,0,0,0.9)",
            align="left",
            namelength=-1,
        ),
        legend=dict(
            x=0.02,
            y=0.98,
            xanchor="left",
            yanchor="top",
            bgcolor="rgba(255,255,255,0)",
            bordercolor="rgba(0,0,0,0)",
            borderwidth=0,
            font=dict(size=12),
        )
    )

    return fig

# create suitable list/array of heat index and temperature for plotting purpose
def create_heat_index_arr(df: pd.DataFrame) -> dict:

    df = df.copy()

    # to accommodate the state where the user change city and subdistrict (at which the brief state produces empty dataframe)
    if df.empty:
        return {
            "x": [],
            "y_hi": [],
            "y_temp": [],
            "y_range": [0, 1],
            "is_empty": True,
            
        }
    df["local_datetime"] = pd.to_datetime(df["local_datetime"], errors="coerce")

    x_ = np.array(df["local_datetime"].dt.to_pydatetime()) # .to_pydatetime() returns datetime objects instead ndarray

    x_values = x_.tolist()
    y_hi = df["heat_index_c"].tolist()
    y_temp = df["temperature_c"].tolist()

    # setting the x and y axis range based on min/max values
    # the max is from HI and min from temperature because HI is generally higher than temperature
    y_min = min(df["heat_index_c"].min(), df["temperature_c"].min())
    y_max = max(df["heat_index_c"].max(), df["temperature_c"].max())

    if y_min == y_max:
        y_min -= 1
        y_max += 1
    else:
        pad = 0.05 * (y_max - y_min)
        y_min -= pad
        y_max += pad
    y_range = [y_min, y_max]

    return {
        "x": x_values,
        "y_hi": y_hi,
        "y_temp": y_temp,
        "y_range": y_range,
        "is_empty": False
    }
