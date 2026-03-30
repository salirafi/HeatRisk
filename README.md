# Jakarta Heat Risk App

This repository contains the source code to build a Python-based web application with Dash Plotly which is intended to show information about heat index and risk for every single ward (kelurahan) in the Jakarta province. The 3-hourly weather forecast data are available for each ward and are provided by Badan Meteorologi, Klimatologi, dan Geofisika (BMKG) through public API described in [Data Terbuka BMKG](https://data.bmkg.go.id/prakiraan-cuaca/).

🎥 [**YOU CAN ACCESS THE LIVE DEMO HERE**](https://jakarta-heat-risk-app.vercel.app/) 🎥

⚠️ **IMPORTANT!** ⚠️  This app is a personal project for data analysis learning, so the BMKG API is not used directly in the app, but rather as database fetching. Also, code might not be optimized for smoother user's experience. For first time loading, the web might take a few seconds.

![Jakarta Heat Risk App](/figures/main_page.png)

## Tools Used

### Backend
- Pandas
- SQLite
- Plotly

### Frontend
- Dash Plotly

## Running

This code is run initially with `python3.11`. Before running the code, make sure all prerequisites are installed. Run in the terminal
```
pip install -r requirements.txt
```
It is recommended to work on virtual environment to isolate project dependencies.

Then, to make sure the weather database is up-to-date, in the parent folder, run
```
python .\fetch\fetch_weather_data.py
```
This might run for around 4 to 5 minutes (see Content section).

Finally, run
```
python app.py
```
to connect to the web app. 

## Notes

Please note that the web app shows the weather forecast from roughly the user's current system time up to 1 day (by default) to the future whenever data is available. If the database is not up-to-date (the database time coverage does not cover the current Jakarta time), then the app pops out a blocker notification prompting the user to update the database.

If the user wants to run [fetch_boundary_data.py](src/fetch_boundary_data.py), make sure they have downloaded the required .gdb file from [here](https://geoservices.big.go.id/portal/apps/webappviewer/index.html?id=cb58db080712468cb4bfd408dbde3d70).

The current default for `current_time` (the "now" time) is set to March 22 2026, 11:00 WIB. This can be changed as necessary.

## Content

```text
.
├── fetch/ 
│   ├── fetch_weather_data.py       # Fetches BMKG weather data
│   ├── build_jakarta_preference.py # Retrieves region codes
│   └── fetch_boundary_data.py      # Loads boundary polygons
|
├── tables/  
│   ├── heat_risk.db               # Main database (weather + boundary data)
│   ├── create_db.py               # Script to initialize database
│
├── assets/                        # Static frontend assets
│   └── (CSS, styling, etc.)
│
├── src/                           
│   └── Built with Dash Plotly  
│
└── app.py                         # Entry point to run the web app with Dash Plotly
```

This project depends heavily on [pandas](https://pandas.pydata.org/) and [SQLite](https://sqlite.org/) environment, though no SQLite broswer needs to be installed since all interface is done with Python.

[fetch](fetch) contains source code for fetching BMKG data ([fetch_weather_data.py](fetch/fetch_weather_data.py)), retrieving region code from [public API](https://wilayah.id/api) ([build_jakarta_preference.py](fetch/build_jakarta_preference.py)), and reading the boundary polygons from RBI data provided by Badan Informasi Geospasial ([fetch_boundary_data.py](fetch/fetch_boundary_data.py)). Note that the only time-dependent data in this repository is the BMKG weather data, so the boundary polygon and region code will always be valid.

[tables](tables) contains SQLite table for boundary polygon and weather data in `heat_risk.db`. The weather data time coverage spans from March 22 2026 11:00 WIB to March 24 2026 20:00 WIB. User can update, or more precisely append, this data by simply running [fetch_weather_data.py](fetch/fetch_weather_data.py) which will append the table with weather data from the user's current time to three days in the future. If there is overlap, the code will replace the old rows (with the same region code and time stamp). Each run will take up about 4 minutes due to polite delay of 1.01 seconds for each of 261 wards in Jakarta to respect BMKG request limit of 60 requests / minute / IP. The file also contains `create_db.py` to create a SQLite database named `heat_risk.db`. There is also a GeoJSON data stored for Choropleth plot.

[assets](assets) contains all the static assets that are used in the app, including the .css file for styling, while [src](src) contains the source code for creating the web app, making use of [Dash Plotly]([https://shiny.posit.co/py/](https://dash.plotly.com/)).

The parent folder contains [app.py](app.py), script to run the web app.

## Author's Remarks

This project was inspired by the tropical condition of Jakarta. Average daytime temperature for downtown Jakarta of about $32\degree$ Celcius ([measurements from 1991 to 2000](https://web.archive.org/web/20231019195817/https://www.nodc.noaa.gov/archive/arc0216/0253808/1.1/data/0-data/Region-5-WMO-Normals-9120/Indonesia/CSV/StasiunMeteorologiKemayoran_96745.csv)) and at a fairly consistent value throughout the year makes its population susceptible to some level of heat risks. This is worsen by the climate change that is getting severe for the past several years, with multiple heat waves reported across the globe (see [here](https://wmo.int/news/media-centre/rising-temperatures-and-extreme-weather-hit-asia-hard) for example). Based on the [U.S. National Weather Service](https://www.weather.gov/ama/heatindex#:~:text=Table_title:%20What%20is%20the%20heat%20index?%20Table_content:,the%20body:%20Heat%20stroke%20highly%20likely%20%7C), temperatures just above $32\degree$ Celcius can start to induce some negative effects on human body such as heat exhaustion, heat cramps, and even heat stroke from prolonged exposure. With many Jakartans working outside, for example as *ojol*, street vendors, or just being stuck in traffic under the scorching sunlight, the risk of these complications may be even greater than realized. 

The use of generative AI includes: Visual Studio Code's Copilot to help tidying up code and writing comments and docstring, as well as OpenAI's Chat GPT to help with code syntax ideas and identify runtime error. Outside of those, including problem formulation and framework of thinking, code logical reasoning and writing, from database management using SQLite to web development using Dash Plotly, all is done mostly by the author. 

## Data Sources

1. Heat index is computed using the regression formula from the US National Weather Service ([see here](https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml) and [here](https://www.weather.gov/ama/heatindex#:~:text=Table_title:%20What%20is%20the%20heat%20index?%20Table_content:,the%20body:%20Heat%20stroke%20highly%20likely%20%7C)), with Celcius to Fahrenheit conversion and vice versa. The formulation is expected to be valid for US sub-tropical region, but its use for tropical region like Indonesia does not guarantee very accurate results. However, as first-order approximation, this is already sufficient.

2. Administrative regional border data is retrieved from RBI10K_ADMINISTRASI_DESA_20230928 database provided by Badan Informasi Geospasial (BIG).

3. Administrative regional code is taken from [wilayah.id](https://wilayah.id/) based on Kepmendagri No 300.2.2-2138 Tahun 2025.

4. Weather forecast data is taken from the public API of Badan Meteorologi, Klimatologi, dan Geofisika (BMKG) accessed via [Data Prakiraan Cuaca Terbuka](https://data.bmkg.go.id/prakiraan-cuaca/).
