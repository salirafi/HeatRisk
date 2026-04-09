#!/usr/bin/env python3
'''
Source code to create the web app.
The app window is built around the current Jakarta time.
'''

from dash import Dash, html, dcc, Input, Output, State, ctx
import pandas as pd

from src.constant import (
    RISK_COLOR_MAP,
    RISK_LABEL_MAP,
    HEAT_RISK_GUIDE,
    WEATHER_ICON_MAP,
    RISK_ABBR
)
from src.helpers import *
from src.plotting import *
from src.db import get_current_jakarta_time # current Jakarta time

boundary_json = load_boundary_data() # city-level boundary GeoJSON dict for the Regional Info page

app = Dash(__name__, suppress_callback_exceptions=True)

EMPTY_FIG = {
    "data": [],
    "layout": {
        "xaxis": {"visible": False},
        "yaxis": {"visible": False},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
    },
}


# HEADER SECTION
def make_header(pathname="/location"):
    
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

            # showing last time DB was updated
            html.Div(
                className="header-meta",
                children=[
                    html.Span("DB last updated ", className="meta-label"),
                    html.Span(get_last_db_update(), className="meta-value"),
                ],
            ),
        ],
    )



# get the nearest available time in the database from the current time
# this is needed since the data is 3-hourly forecast
def get_nearest_current_time_from_store(times_data):
    times = deserialize_timestamps(times_data)
    if not times:
        return None
    times_series = pd.Series(times)
    current_time = get_current_jakarta_time()
    nearest_idx  = (times_series - current_time).abs().idxmin()
    return pd.Timestamp(times_series.loc[nearest_idx])


def get_default_query_window():
    current_time = get_current_jakarta_time()
    return {
        "start_time": current_time,
        "end_time":   current_time + pd.Timedelta(days=2.0), # default queried database has time coverage of 2 days
    }

# get the available timestamps from the queried window
def load_forecast_times():
    window     = get_default_query_window()

    # 3 hours offset to start_time is to include the timestamp corresponds to the exact current time
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
        # this ideally should output only a single row since combination of code and timestamp is unique
        adm4 = get_adm4_for_ward(selected_ward, conn)
        if adm4 is None:
            return pd.DataFrame()
        snap = current_condition(adm4, nearest_time, conn)
    finally:
        conn.close()
    return snap

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
        adm4 = get_adm4_for_ward(selected_ward, conn)
        if adm4 is None:
            return pd.DataFrame()
        df = future_forecast(adm4, current_time_df, end_time, conn)
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


# ===================
#  Page Layouts
# ===================

# options to be displayed to the search bar
# all available wards will be listed
def load_search_options():
    conn = get_conn()
    try:
        return make_ward_search_options(conn)
    finally:
        conn.close()


options = load_search_options()

def location_layout():
    return html.Div(
        className="right-panel",
        children=[
            # search bar row
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
            # dynamic
            html.Div(id="location_content_ui", className="location-body"),
        ],
    )

def map_layout():
    return html.Div(
        className="right-panel right-panel-map",
        children=[
            # time slider
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
            # map side-by-side
            html.Div(
                className="map-content-row",
                children=[
                    html.Div(
                        className="map-section map-section-full",
                        children=[
                            dcc.Graph(
                                id="heat_risk_map", figure=EMPTY_FIG,
                                config={"displayModeBar": False},
                                style={"height": "100%", "width": "100%"},
                            ),
                            html.Div(id="map_legend", className="legend-container"),
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
                    id="evolution_timeline_ui", figure=EMPTY_FIG,
                    config={"displayModeBar": False},
                    style={"height": "100%", "width": "100%"},
                ),
            ],
        ),
    ]


# ===================
#  Root Layout
# ===================

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
                                            "Go to project repo",
                                            href="https://github.com/salirafi/Jakarta-Heat-Risk-App",
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


# ========================
#  Callback Functions
# ========================


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
    Output("evolution_timeline_ui", "figure"),
    Input("selected_ward_search",   "value"),
    Input("forecast-times-store",   "data"),
)
def evolution_timeline_ui(selected_ward, times_data):
    if not selected_ward:
        return {}
    df = load_future_forecast_df(selected_ward, times_data)
    if df.empty:
        return {}
    fig = build_heat_index_plot(df=df.head(6).copy())
    fig.update_layout(uirevision="weather-timeline")
    return fig

# callback for displaying the current time and database's timestamp
@app.callback(
    Output("current_snapshot_time_text", "children"),
    Input("selected_ward_search",        "value"),
    Input("forecast-times-store",        "data"),
)
def current_snapshot_time_text(selected_ward, times_data):
    current_time = get_current_jakarta_time()
    current_time_text = current_time.strftime('%b %d, %H:%M')

    # if no ward selected, show placeholder "-"
    if not selected_ward:
        data_time_text = "—"
    else:
        data_time = get_nearest_current_time_from_store(times_data)
        data_time_text = "—" if data_time is None else data_time.strftime('%b %d, %H:%M')

    return html.Div(
        className="time-meta-card",
        children=[
            html.Div("Current Jakarta Time", className="time-meta-label"),
            html.Div(current_time_text, className="time-meta-now"),
            html.Div(
                [
                    html.Span("Forecast snapshot", className="time-meta-data-label"),
                    html.Span(data_time_text, className="time-meta-data-value"),
                ],
                className="time-meta-data",
            ),
        ],
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
        colormap = create_dynamic_colormap(
            selected_time=selected_time,
            # boundary_geojson=boundary_json,
            conn=conn,
        )
    finally:
        conn.close()
    fig = build_map_figure(
        boundary_geojson=boundary_json,
        # locations=colormap["locations"],
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
    Output("guide-modal", "className"),
    Output("modal-content", "children"),
    Input("url", "pathname"),
    Input("guide-btn-1", "n_clicks"),
    Input("guide-btn-2", "n_clicks"),
    Input("guide-btn-3", "n_clicks"),
    Input("guide-btn-4", "n_clicks"),
    Input("guide-btn-5", "n_clicks"),
    Input("modal-close", "n_clicks"),
    prevent_initial_call=False,
)
def toggle_modal(_pathname, b1, b2, b3, b4, b5, close_clicks):
    trigger = ctx.triggered_id


    level_map = {
        "guide-btn-1": "Lower Risk",
        "guide-btn-2": "Caution",
        "guide-btn-3": "Extreme Caution",
        "guide-btn-4": "Danger",
        "guide-btn-5": "Extreme Danger",
    }
    level = level_map.get(trigger)

    if level is None:
        return "modal-overlay", ""

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
    return "modal-overlay modal-show", modal_body

if __name__ == "__main__":
    app.run()
