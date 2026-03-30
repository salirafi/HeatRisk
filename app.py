#!/usr/bin/env python3
'''
Source code to create the web app.
Note that the pipeline of the code, in default, does not allow outputs of past weather data.
This can be changed by changing current_time variable, but note that the definition of 'current time' will not mean the present time anymore.
'''

from dash import Dash, html, dcc, Input, Output, State, ctx
import pandas as pd

from src.constant import (
    RISK_COLOR_MAP,
    RISK_LABEL_MAP,
    HEAT_RISK_GUIDE,
    WEATHER_ICON_MAP,
    RISK_ABBR,
    WEATHER_TABLE,
)
from src.helpers import *
from src.plotting import *

boundary_json = load_boundary_data() # pd.DataFrame and JSON dict
# current_time  = pd.Timestamp.now(tz="Asia/Jakarta").tz_localize(None) # definition of current_time
current_time = pd.Timestamp(year=2026, month=3, day=22, hour=11)

app = Dash(__name__, suppress_callback_exceptions=True)

# helper to make the header section
def make_header(pathname="/location"):
    # divide the app into two pages
    location_active = "nav-link active" if pathname in ["/", "/location"] else "nav-link"
    map_active      = "nav-link active" if pathname == "/map" else "nav-link"

    return html.Header(
        className="top-header",
        children=[

            html.Div(
                className="header-brand",
                children=[
                    html.Span("Jakarta", className="brand-accent"),
                    html.Span(" Heat Risk", className="brand-main"),
                ],
            ),

            # nav section
            html.Nav(
                className="header-nav",
                children=[
                    dcc.Link("Ward Info",     href="/location", className=location_active),
                    dcc.Link("Regional Info", href="/map",      className=map_active),
                ],
            ),

            # showing text "DB updated"
            html.Div(
                className="header-meta",
                children=[
                    html.Span("DB updated ", className="meta-label"),
                    html.Span(get_last_db_update(), className="meta-value"),
                ],
            ),
        ],
    )


# ##############
#  Helpers Related to Data
# ##############

# get the nearest available time in the database from the current time
def get_nearest_current_time_from_store(times_data):
    times = deserialize_timestamps(times_data)
    if not times:
        return None
    times_series = pd.Series(times)
    nearest_idx  = (times_series - current_time).abs().idxmin()
    return pd.Timestamp(times_series.loc[nearest_idx])

# default queried database has time coverage of 1 day
def get_default_query_window():
    return {
        "start_time": current_time,
        "end_time":   current_time + pd.Timedelta(days=1.0),
    }

# get the available timestamps from the queried window
def load_forecast_times():
    window     = get_default_query_window()

    # 3 hours offset to start_time is ti include the timestamp corresponds to the exact current time
    # if no offset, the earliest timestamp queried will be AFTER the current time
    start_time = pd.to_datetime(window["start_time"]) - pd.Timedelta(hours=3.0)
    end_time   = pd.to_datetime(window["end_time"])   + pd.Timedelta(hours=3.0)
    conn = get_conn()
    try:
        times = available_timestamps(start_time, end_time, conn)
    finally:
        conn.close()
    return times

# query weather data of current time and selected location
def load_current_snapshot_df(selected_ward, times_data):
    if not selected_ward:
        return pd.DataFrame()
    nearest_time = get_nearest_current_time_from_store(times_data)
    if nearest_time is None:
        return pd.DataFrame()
    conn = get_conn()
    try:
        # this ideally should output only a single row 
        # since combination of code and timestamp is unique
        df_region = pd.read_sql_query(
            f"SELECT adm4 FROM {WEATHER_TABLE} WHERE desa_kelurahan = ? LIMIT 1",
            conn, params=[selected_ward],
        )
        if df_region.empty:
            return pd.DataFrame()
        snap = current_condition(df_region.iloc[0]["adm4"], nearest_time, conn)
    finally:
        conn.close()
    return snap

# get data for evolution plot
def load_heat_index_evolution_values(selected_ward, times_data):
    df = load_future_forecast_df(selected_ward, times_data)
    if df.empty:
        return None
    return create_heat_index_arr(df) # create the suitable array structure for plotting

# load future forecast dataframe for a selected ward 
# between nearest current forecast time and the query window end time
def load_future_forecast_df(selected_ward, times_data):
    if not selected_ward:
        return pd.DataFrame()
    
    # this df will correspond to the nearest future timestamp to current time
    current_time_df = get_nearest_current_time_from_store(times_data)
    if current_time_df is None:
        return pd.DataFrame()
    end_time = get_default_query_window()["end_time"] # plus 1-day (default) from start_time
    conn = get_conn()
    try:
        df_region = pd.read_sql_query(
            # do SQL query to retrieve time, HI, risk level, and ward
            f"SELECT adm4 FROM {WEATHER_TABLE} WHERE desa_kelurahan = ? LIMIT 1",
            conn, params=[selected_ward],
        )
        if df_region.empty:
            return pd.DataFrame()
        df = future_forecast(df_region.iloc[0]["adm4"], current_time_df, end_time, conn)
    finally:
        conn.close()
    return df

# ##################
#  UI Component
# #################

# creating the future forecast cards
def build_forecast_cards(df):
    if df.empty:
        return html.Div("No available data.", className="empty-note")

    cards = []
    for ward, ts_, hi_, risk_ in zip(
        df["desa_kelurahan"], df["local_datetime"],
        df["heat_index_c"],   df["risk_level"],
    ):
        #  color the cards' background to the risk level
        bg_color = hex_to_rgba_css(RISK_COLOR_MAP.get(risk_, "#dcdcdc"), alpha=0.15)
        cards.append(
            html.Div(
                className="forecast-card",
                style={"background": bg_color},
                children=[
                    html.Div(str(ward),                                    className="fc-ward"),
                    html.Div(pd.Timestamp(ts_).strftime("%b %d, %H:%M"),   className="fc-time"),
                    html.Div(f"HI: {hi_:.1f} °C",                          className="fc-hi"),
                    html.Div(risk_badge(risk_),                             className="fc-risk"),
                ],
            )
        )
    return html.Div(cards, className="forecast-scroll")

def build_map_legend():
    levels = [
        "No Data",
        "Lower Risk",
        "Caution",
        "Extreme Caution",
        "Danger",
        "Extreme Danger",
    ]
    return html.Div(
        className="legend-row",
        children=[
            html.Div(
                className="legend-item",
                children=[
                    html.Span(
                        className="legend-dot",
                        style={"backgroundColor": RISK_COLOR_MAP[level]},
                    ),
                    html.Span(RISK_LABEL_MAP.get(level, level), className="legend-label"),
                ],
            )
            for level in levels
        ],
    )

def build_metric_card(label, value, extra_class=""):
    return html.Div(
        className=f"metric-card {extra_class}".strip(),
        children=[
            html.Div(label, className="metric-label"),
            html.Div(value, className="metric-value"),
        ],
    )

# function to construct the heat risk guide section
def build_heat_risk_guide():
    levels = ["Lower Risk", "Caution", "Extreme Caution", "Danger", "Extreme Danger"]
    return html.Div(
        className="guide-section",
        children=[
            html.Div("Heat Risk Guide", className="sidebar-section-title"),
            html.P(
                [
                    "Based on the ",
                    html.A(
                        "U.S. National Weather Service",
                        href="https://www.wpc.ncep.noaa.gov/heatrisk/",
                        target="_blank",
                        className="inline-link",
                    ),
                    " heat risk framework.",
                ],
                className="sidebar-caption",
            ),
            html.Div(
                className="guide-list",
                children=[
                    html.Button(
                        children=[
                            html.Span(
                                className="guide-item-left",
                                children=[
                                    html.Span(
                                        className="risk-dot",
                                        style={"background": RISK_COLOR_MAP[level]},
                                    ),
                                    html.Span(
                                        RISK_LABEL_MAP.get(level, level),
                                        className="guide-item-label",
                                    ),
                                ],
                            ),
                            html.Span("View →", className="guide-item-cta"),
                        ],
                        id=f"guide-btn-{idx}",
                        className="guide-btn",
                    )
                    for idx, level in enumerate(levels, start=1)
                ],
            ),
        ],
    )


# ───────────
#  Page Layouts
# ───────────

# options to be displayed to the search bar
# all available wards will be listed
options = make_ward_search_options(get_conn())

def location_layout():
    return html.Div(
        className="right-panel",
        children=[
            # ── Search bar row ──
            html.Div(
                className="search-bar-row",
                children=[
                    html.Div(id="current_snapshot_time_text", className="time-meta"),
                    html.Div(
                        className="search-wrap",
                        children=[
                            dcc.Dropdown(
                                id="selected_ward_search",
                                options=options,
                                placeholder="Search ward…",
                                searchable=True,
                                clearable=True,
                                className="ward-dropdown",
                            ),
                        ],
                    ),
                    html.Div(className="search-spacer"),
                ],
            ),
            # ── Dynamic content ──
            html.Div(id="location_content_ui", className="location-body"),
        ],
    )

def map_layout():
    return html.Div(
        className="right-panel right-panel-map",
        children=[
            # Time slider
            html.Div(
                className="slider-row",
                children=[
                    html.Div(id="selected_map_time_text", className="map-time-caption"),
                    html.Div(
                        className="slider-wrap",
                        children=[
                            dcc.Slider(
                                id="selected_time_idx",
                                min=0, max=0, step=1, value=0,
                                marks={}, allow_direct_input=False,
                            ),
                        ],
                    ),
                ],
            ),
            # Map + summary side-by-side
            html.Div(
                className="map-content-row",
                children=[
                    html.Div(
                        className="map-section",
                        children=[
                            dcc.Graph(
                                id="heat_risk_map", figure={},
                                config={"displayModeBar": False},
                                style={"height": "100%", "width": "100%"},
                            ),
                            html.Div(id="map_legend", className="legend-container"),
                        ],
                    ),
                    html.Div(
                        className="map-section summary-section",
                        children=[
                            html.Div(
                                className="summary-center",
                                children=[
                                    dcc.Graph(
                                        id="city_summary_plot", figure={},
                                        config={"displayModeBar": False},
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

# create instance when users don't select ward
def build_empty_location_state():
    return html.Div(
        children=[
            html.Div("🌡", className="empty-icon"),
            html.Div("Select a ward to view heat risk data.", className="empty-text"),
        ],
        className="empty-state",
    )

def build_location_content():
    return [
        # current metrics cards
        html.Div(id="current_metrics_ui", className="metrics-row"),

        # forecast cards (horizontal scroll)
        html.Div(
            className="forecast-section",
            children=[
                html.Div(id="future_forecast_cards_ui", className="forecast-scroll-wrap"),
            ],
        ),

        # heat index evolution plot
        html.Div(
            className="evolution-section",
            children=[
                dcc.Graph(
                    id="heat_index_evolution_plot", figure={},
                    config={"displayModeBar": False},
                    style={"height": "100%", "width": "100%"},
                ),
                html.Div(
                    "*Gap between heat index and temperature reflects humidity.",
                    className="plot-note",
                ),
            ],
        ),
    ]


# ##############
#  Root Layout
# #############

app.layout = html.Div(
    className="app-shell",
    children=[
        dcc.Location(id="url"),
        dcc.Store(id="forecast-times-store"),
        dcc.Store(id="startup-modal-seen", data=False, storage_type="session"), # start-up modal; comment out this

        html.Div(id="header-container"),

        html.Div(
            className="page-body",
            children=[

                # SIDEBAR ON THE LEFT
                html.Aside(
                    className="sidebar",
                    children=[
                        html.Div(
                            className="sidebar-inner",
                            children=[
                                build_heat_risk_guide(),

                                html.Hr(className="sidebar-divider"),

                                html.Div("About", className="sidebar-section-title"),

                                dcc.Markdown(
                                    """
Heat index is computed using the regression formula from the
[US National Weather Service](https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml).
The formula is calibrated for US sub-tropical conditions; accuracy for
tropical regions like Indonesia is approximate, but sufficient as a
first-order estimate.
                                    """,
                                    className="sidebar-about",
                                ),

                                dcc.Markdown(
                                    """
Weather data from BMKG's
[Data Prakiraan Cuaca Terbuka](https://data.bmkg.go.id/prakiraan-cuaca/)
via free public API.
                                    """,
                                    className="sidebar-about",
                                ),

                                html.Div(
                                    className="sidebar-footer",
                                    children=[
                                        html.Img(src="/assets/github.svg", className="footer-icon"),
                                        html.A(
                                            "salirafi",
                                            href="https://github.com/salirafi",
                                            target="_blank",
                                            className="footer-link",
                                        ),
                                    ],
                                ),
                            ],
                        )
                    ],
                ),

                # MAIN CONTENT ON THE RIGHT
                html.Main(id="page-container", className="main-content"),
            ],
        ),

        dcc.Store(id="guide-modal-store", data=False),
        html.Div(
            id="guide-modal",
            className="modal-overlay",
            children=[
                html.Div(
                    className="modal-box",
                    children=[
                        html.Button("×", id="modal-close", className="modal-close-btn"),
                        html.Div(id="modal-content", className="modal-body"),
                    ],
                )
            ],
        ),
    ],
)


# ###################
#  Callback Functions
# ################

# # callbak for showing start-up modal; comment this in the future
# @app.callback(
#     Output("guide-modal", "className", allow_duplicate=True),
#     Output("modal-content", "children", allow_duplicate=True),
#     Output("startup-modal-seen", "data"),
#     Input("url", "pathname"),
#     State("startup-modal-seen", "data"),
#     prevent_initial_call=False,
# )
# def show_startup_modal(_pathname, seen):
#     if seen:
#         return "modal-overlay", "", True

#     modal_body = html.Div(
#         children=[
#             html.Div("Notice", className="modal-risk-title"),
#             html.Div(
#                 "The default current time is currently set to a fixed value, not the real live current time due to the use of local SQLite database. This will be changed in the future.",
#                 className="modal-section-text",
#             ),
#         ]
#     )
#     return "modal-overlay modal-show", modal_body, True

@app.callback(
    Output("header-container", "children"),
    Output("page-container",   "children"),
    Input("url", "pathname"),
)
def render_page(pathname):
    pathname = pathname or "/location"
    header   = make_header(pathname)
    if pathname == "/map":
        return header, map_layout() # switching between pages
    return header, location_layout()

@app.callback(
    Output("forecast-times-store", "data"),
    Input("url", "pathname"),
)
def forecast_times_store(_pathname):
    times = load_forecast_times()
    return serialize_timestamps(times)

@app.callback(
    Output("location_content_ui", "children"),
    Input("selected_ward_search", "value"),
)
def location_content_ui(selected_ward):
    if not selected_ward:
        return build_empty_location_state() # if no selected ward, display text
    return build_location_content() # else display data

@app.callback(
    Output("current_metrics_ui", "children"),
    Input("selected_ward_search", "value"),
    Input("forecast-times-store", "data"),
)
def current_metrics_ui(selected_ward, times_data):
    if not selected_ward:
        return []
    snap = load_current_snapshot_df(selected_ward, times_data)
    if snap.empty:
        return html.Div("No data for the selected region.", className="empty-note")

    row = snap.iloc[0]
    return [
        html.Div(
            className="metric-card",
            children=[
                html.Div("Temperature",              className="metric-label"),
                html.Div(f"{row['temperature_c']:.1f}°C", className="metric-value"),
            ],
        ),
        html.Div(
            className="metric-card",
            children=[
                html.Div("Humidity",                    className="metric-label"),
                html.Div(f"{row['humidity_ptg']:.1f}%", className="metric-value"),
            ],
        ),
        html.Div(
            className="metric-card",
            children=[
                html.Div("Heat Index",                   className="metric-label"),
                html.Div(f"{row['heat_index_c']:.1f}°C", className="metric-value"),
            ],
        ),
        html.Div(
            className="metric-card",
            children=[
                html.Div("Risk Level", className="metric-label"),
                html.Div(
                    # using the abbreviation for each risk level for short text
                    # see the heat risk guide or RISK_ABBR for the corresponding abbreviation
                    RISK_ABBR.get(row["risk_level"], row["risk_level"]),
                    className="metric-value",
                ),
            ],
        ),
        html.Div(
            className="metric-card",
            children=[
                html.Div("Weather", className="metric-label"),
                html.Img(
                    src=f"/assets/{WEATHER_ICON_MAP.get(row['weather_desc'], 'cloudy.svg')}",
                    className="weather-icon",
                ),
            ],
        ),
    ]

@app.callback(
    Output("future_forecast_cards_ui", "children"),
    Input("selected_ward_search",      "value"),
    Input("forecast-times-store",      "data"),
)
def future_forecast_cards_ui(selected_ward, times_data):
    if not selected_ward:
        return []
    df = load_future_forecast_df(selected_ward, times_data)
    return build_forecast_cards(df)

@app.callback(
    Output("heat_index_evolution_plot", "figure"),
    Input("selected_ward_search",       "value"),
    Input("forecast-times-store",       "data"),
)
def heat_index_evolution_plot(selected_ward, times_data):
    if not selected_ward:
        return {}
    evolution_values = load_heat_index_evolution_values(selected_ward, times_data)
    if evolution_values is None:
        return {}
    fig = build_heat_index_plot(evolution_values=evolution_values)

    # this does not change the UI, so it should be faster to load
    fig.update_layout(uirevision="heat-index-evolution")
    return fig

# callback for displaying the current time and database's timestamp
@app.callback(
    Output("current_snapshot_time_text", "children"),
    Input("selected_ward_search",        "value"),
    Input("forecast-times-store",        "data"),
)
def current_snapshot_time_text(selected_ward, times_data):

    # if no ward selected, show placeholder "-"
    if not selected_ward:
        return f"Now: {current_time.strftime('%b %d, %H:%M')}  ·  Data: —"
    data_time = get_nearest_current_time_from_store(times_data)
    if data_time is None:
        return f"Now: {current_time.strftime('%b %d, %H:%M')}  ·  Data: —"
    return (
        f"Now: {current_time.strftime('%b %d, %H:%M')}  ·  "
        f"Data: {data_time.strftime('%b %d, %H:%M')}"
    )

@app.callback(
    Output("selected_time_idx", "min"),
    Output("selected_time_idx", "max"),
    Output("selected_time_idx", "value"),
    Output("selected_time_idx", "marks"),
    Input("forecast-times-store", "data"),
)
def time_slider(store_data):
    timestamps = deserialize_timestamps(store_data)
    if not timestamps:
        return 0, 0, 0, {}
    marks       = build_slider_marks(timestamps)
    return 0, len(timestamps) - 1, 0, marks # numbering marks (but later not shown in the app)

@app.callback(
    Output("selected_map_time_text", "children"),
    Input("selected_time_idx",       "value"),
    Input("forecast-times-store",    "data"),
)
def selected_map_time_text(selected_idx, store_data):
    selected_time = get_selected_time_from_store(selected_idx, store_data)
    if selected_time is None:
        return "Map time: —"
    return f"Map time: {selected_time.strftime('%b %d  %H:%M')}"

@app.callback(
    Output("heat_risk_map",       "figure"),
    Input("selected_time_idx",    "value"),
    State("forecast-times-store", "data"),
)
def heat_risk_map(selected_idx, times_data):
    selected_time = get_selected_time_from_store(selected_idx, times_data)
    if selected_time is None:
        return {}
    conn = get_conn()
    try:
        colormap = create_dynamic_colormap(selected_time=selected_time, conn=conn)
    finally:
        conn.close()
    fig = build_map_figure(
        boundary_geojson=boundary_json,
        locations=colormap["customdata"][:, -1].tolist(),
        colormap=colormap,
    )

    # this does not change the UI, so it should be faster to load
    fig.update_layout(uirevision="heat-risk-map")
    return fig

@app.callback(
    Output("map_legend",          "children"),
    Input("selected_time_idx",    "value"),
)
def map_legend(_):
    return build_map_legend()

@app.callback(
    Output("city_summary_plot",   "figure"),
    Input("selected_time_idx",    "value"),
    State("forecast-times-store", "data"),
)
def city_summary_plot(selected_idx, times_data):
    selected_time = get_selected_time_from_store(selected_idx, times_data)
    if selected_time is None:
        return {}
    conn = get_conn()
    try:
        summary = city_summary_at_time(selected_time=selected_time, conn=conn)
    finally:
        conn.close()
    fig = build_city_summary_plot(summary_value=summary)

    # this does not change the UI, so it should be faster to load
    fig.update_layout(uirevision="city-summary")
    return fig

@app.callback(
    Output("guide-modal", "className"),
    Output("modal-content", "children"),
    Output("startup-modal-seen", "data"),
    Input("url", "pathname"),
    Input("guide-btn-1", "n_clicks"),
    Input("guide-btn-2", "n_clicks"),
    Input("guide-btn-3", "n_clicks"),
    Input("guide-btn-4", "n_clicks"),
    Input("guide-btn-5", "n_clicks"),
    Input("modal-close", "n_clicks"),
    State("startup-modal-seen", "data"),
    prevent_initial_call=False,
)
def toggle_modal(_pathname, b1, b2, b3, b4, b5, close_clicks, startup_seen):
    trigger = ctx.triggered_id

    # show startup modal only once per browser session; comment this in the future
    if trigger in (None, "url") and not startup_seen:
        modal_body = html.Div(
            children=[
                html.Div(
                    "⚠️ Important ⚠️",
                    style={
                        "fontWeight": "700",
                        "fontSize": "1.4rem",
                        "marginBottom": "10px"
                    }
                ),
                html.Div(
                    "The default current time is currently set to a fixed value (March 22, 2026 11:00 WIB), not the real live current time due to the use of local SQLite database. This will be changed in the future.",
                    className="modal-section-text",
                ),
            ]
        )
        return "modal-overlay modal-show", modal_body, True

    # close modal
    if trigger == "modal-close":
        return "modal-overlay", "", startup_seen

    level_map = {
        "guide-btn-1": "Lower Risk",
        "guide-btn-2": "Caution",
        "guide-btn-3": "Extreme Caution",
        "guide-btn-4": "Danger",
        "guide-btn-5": "Extreme Danger",
    }
    level = level_map.get(trigger)

    if level is None:
        return "modal-overlay", "", startup_seen

    guide = HEAT_RISK_GUIDE[level]

    modal_body = html.Div(
        children=[
            html.Div(
                className="modal-header",
                children=[
                    html.Span(
                        className="risk-dot modal-risk-dot",
                        style={"background": RISK_COLOR_MAP[level]},
                    ),
                    html.Div(
                        [
                            html.Div(
                                RISK_LABEL_MAP.get(level, level),
                                className="modal-risk-title",
                            ),
                            html.Div(guide["level"], className="modal-risk-sub"),
                        ]
                    ),
                ],
            ),
            html.Div(
                className="modal-section",
                children=[
                    html.Div("What to expect", className="modal-section-label"),
                    html.Div(guide["expect"], className="modal-section-text"),
                ],
            ),
            html.Div(
                className="modal-section",
                children=[
                    html.Div("Recommended actions", className="modal-section-label"),
                    html.Div(guide["do"], className="modal-section-text"),
                ],
            ),
        ]
    )
    return "modal-overlay modal-show", modal_body, startup_seen

if __name__ == "__main__":
    app.run()
