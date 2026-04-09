from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
BOUNDARY_TABLE = "city_boundary_table_simplified"
WEATHER_TABLE = "ward_weather_table"
CITY_SUMMARY_TABLE = "city_summary_table"
BOUNDARY_GEOJSON_PATH = BASE_DIR / "tables" / "jakarta_boundary_simplified.geojson"

RISK_ORDER = [
    "No Data",
    "Lower Risk",
    "Caution",
    "Extreme Caution",
    "Danger",
    "Extreme Danger",
]
RISK_LABEL_MAP = {
    "No Data": "No Data",
    "Lower Risk": "Lower Risk (LR)",
    "Caution": "Caution (C)",
    "Extreme Caution": "Extreme Caution (EC)",
    "Danger": "Danger (D)",
    "Extreme Danger": "Extreme Danger (ED)",
}
RISK_ABBR = {
    "No Data": "ND",
    "Lower Risk": "LR",
    "Caution": "C",
    "Extreme Caution": "EC",
    "Danger": "D",
    "Extreme Danger": "ED",
    "Lower Risk (LR)": "LR",
    "Caution (C)": "C",
    "Extreme Caution (EC)": "EC",
    "Danger (D)": "D",
    "Extreme Danger (ED)": "ED",
}
RISK_COLOR_MAP = {
    "No Data": "#dcdcdc",

    # original labels
    "Lower Risk": "#66bb6a",
    "Caution": "#ffee58",
    "Extreme Caution": "#ffa726",
    "Danger": "#ef5350",
    "Extreme Danger": "#9c27b0",

    # display labels with abbreviations
    "Lower Risk (LR)": "#66bb6a",
    "Caution (C)": "#ffee58",
    "Extreme Caution (EC)": "#ffa726",
    "Danger (D)": "#ef5350",
    "Extreme Danger (ED)": "#9c27b0",
}
RISK_CODE_MAP = {
    "No Data": 0,
    "Lower Risk": 1,
    "Caution": 2,
    "Extreme Caution": 3,
    "Danger": 4,
    "Extreme Danger": 5,
    "Lower Risk (LR)": 1,
    "Caution (C)": 2,
    "Extreme Caution (EC)": 3,
    "Danger (D)": 4,
    "Extreme Danger (ED)": 5,
}

WEATHER_ICON_MAP = {
    "Sunny": "day_clear.svg",
    "Partly Cloudy": "day_partial_cloud.svg",
    "Cloudy": "cloudy.svg",
    "Light Rain": "rain.svg",
    "Rain": "rain.svg",
    "Thunderstorm": "rain_thunder.svg",
}

CITY_COLOR_MAP = {
    "Jakarta Barat": "#1f77b4",
    "Jakarta Pusat": "#17becf",
    "Jakarta Selatan": "#8c564b",
    "Jakarta Timur": "#7f7f7f",
    "Jakarta Utara": "#393b79",
} 
CITY_ORDER = [
    "Jakarta Barat",
    "Jakarta Pusat",
    "Jakarta Selatan",
    "Jakarta Timur",
    "Jakarta Utara",
]

HEAT_RISK_GUIDE = {
    "Lower Risk": {
        "level": "Level 0 · Little to None",
        "expect": (
            "This level of heat poses little to no elevated risk for most people. "
            "It is a very common level of heat and usually does not require special precautions."
        ),
        "do": (
            "No special preventive action is usually needed. "
            "Basic hydration and normal heat awareness are enough."
        ),
    },
    "Caution": {
        "level": "Level 1 · Minor",
        "expect": (
            "Most people can tolerate this heat, but there is a minor risk of heat-related effects "
            "for people who are extremely heat-sensitive and those without effective cooling or enough hydration."
        ),
        "do": (
            "Increase hydration, reduce time outdoors during the strongest sun, stay in the shade, "
            "and use cooler nighttime air when possible."
        ),
    },
    "Extreme Caution": {
        "level": "Level 2 · Moderate",
        "expect": (
            "Many people can still tolerate this heat, but the risk becomes more noticeable for "
            "heat-sensitive groups especially those without effective cooling or hydration, visitors not acclimated to the heat, and people spending long "
            "periods outside. Heat-related illness can begin to occur."
        ),
        "do": (
            "Reduce time in the sun during the warmest part of the day, stay hydrated, stay in a cool "
            "place, and move outdoor activities to cooler hours."
        ),
    },
    "Danger": {
        "level": "Level 3 · Major",
        "expect": (
            "This is a major heat risk. Dangerous conditions can affect a much larger part of the "
            "population, especially anyone active in the sun or without proper cooling and hydration."
        ),
        "do": (
            "Consider canceling outdoor activity during the hottest part of the day, stay hydrated, "
            "remain in cooler indoor places, and use air conditioning if available. Fans alone may not be enough."
        ),
    },
    "Extreme Danger": {
        "level": "Level 4 · Extreme",
        "expect": (
            "This is a rare and extreme level of heat risk. It often reflects a prolonged multi-day "
            "heat event and can be dangerous for the entire population, especially without cooling."
        ),
        "do": (
            "Strongly consider canceling outdoor activities, stay hydrated, stay in a cool place "
            "including overnight, use air conditioning if available, and check on neighbors or other vulnerable people."
        ),
    },

}
