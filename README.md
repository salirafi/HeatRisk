# Jakarta Heat Risk App

This repository contains the source code to build a Python-based web application with Dash Plotly which is intended to show information about heat index and risk for every single ward (kelurahan) in the Jakarta province. The 3-hourly weather forecast data are available for each ward and are provided by Badan Meteorologi, Klimatologi, dan Geofisika (BMKG) through public API described in [Data Terbuka BMKG](https://data.bmkg.go.id/prakiraan-cuaca/).

🎥 [**YOU CAN ACCESS THE LIVE DEMO HERE**](https://jakarta-heat-risk-app.vercel.app/) 🎥

⚠️ **IMPORTANT!** ⚠️  
- The app requires a cloud-hosted MySQL database and uses the live Jakarta time to choose the nearest available forecast snapshot. Missing database environment variables or an unreachable MySQL server will cause the app to raise an error immediately.
- The app currently refreshes BMKG data on a 36-hour cron schedule, so it does not fetch live data during user interaction, which mainstream weather apps usually do. This will be improved in a future version.

![Jakarta Heat Risk App](/figures/main_page.png)


## Tools Used

### Backend
- Pandas
- MySQL
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

For deployed environments such as Vercel, set the database credentials as environment variables and configure `CRON_SECRET`. The included `vercel.json` triggers `/api/cron_refresh` once per day, and the refresh handler only performs a real sync when the latest successful upload is older than 36 hours by default.

Finally, run
```
python app.py
```
to connect to the web app. 

If the user wants to run [fetch_boundary_data.py](src/fetch_boundary_data.py), make sure they have downloaded the required .gdb file from [HERE](https://geoservices.big.go.id/portal/apps/webappviewer/index.html?id=cb58db080712468cb4bfd408dbde3d70).

## Content

```text
.
├── fetch/ 
│   ├── fetch_weather_data.py       # Fetches BMKG weather data
│   ├── build_jakarta_preference.py # Retrieves region codes
│   └── fetch_boundary_data.py      # Loads boundary polygons
|
├── tables/  
│   ├── jakarta_city_boundary_simplified.geojson    # Polygon data for city-level boundary
│   ├── jakarta_boundary_simplified.geojson         # Polygon data for ward-level boundary
│
├── assets/                        # Static frontend assets
│   ├── style.css                  # CSS styling
│   └── ...   
│
├── src/                           
│   ├── constant.py                # Global variables for app.py
│   ├── db.py                      # Helpers for MySQL connection
│   ├── helpers.py                  
│   └── plotting.py                # Helpers for plotting functions
│
├── api/
│   ├── cron_refresh.py            # Perform cron job for Vercel
│
└── app.py                         # Entry point for Dash Plotly web app
```

Note that the only time-dependent data in this project is the BMKG weather data, so the boundary polygon and region code will always be static values.

The weather fetch pipeline uploads directly to a cloud MySQL database. Each BMKG refresh run takes about 4 minutes due to the polite delay of 1.01 seconds for each of 261 wards in Jakarta to respect BMKG request limit of 60 requests / minute / IP.


## Author's Remarks

This project was inspired by the tropical condition of Jakarta. Average daytime temperature for downtown Jakarta of about $32\degree$ Celcius ([measurements from 1991 to 2000](https://web.archive.org/web/20231019195817/https://www.nodc.noaa.gov/archive/arc0216/0253808/1.1/data/0-data/Region-5-WMO-Normals-9120/Indonesia/CSV/StasiunMeteorologiKemayoran_96745.csv)) and at a fairly consistent value throughout the year makes its population susceptible to some level of heat risks. This is worsen by the climate change that is getting severe for the past several years, with multiple heat waves reported across the globe (see [here](https://wmo.int/news/media-centre/rising-temperatures-and-extreme-weather-hit-asia-hard) for example). Based on the [U.S. National Weather Service](https://www.weather.gov/ama/heatindex#:~:text=Table_title:%20What%20is%20the%20heat%20index?%20Table_content:,the%20body:%20Heat%20stroke%20highly%20likely%20%7C), temperatures just above $32\degree$ Celcius can start to induce some negative effects on human body such as heat exhaustion, heat cramps, and even heat stroke from prolonged exposure. With many Jakartans working outside, for example as *ojol*, street vendors, or just being stuck in traffic under the scorching sunlight, the risk of these complications may be even greater than realized. 

The use of generative AI includes: Github Copilot to help in code syntax and comments/docstring writing, as well as OpenAI's Chat GPT to help with identifying bugs and errors. Outside of those, including problem formulation and framework of thinking, code logical reasoning and writing, from database management to web development using Flask, all is done mostly by the author.

## Data Sources

1. Heat index is computed using the regression formula from the US National Weather Service ([see here](https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml) and [here](https://www.weather.gov/ama/heatindex#:~:text=Table_title:%20What%20is%20the%20heat%20index?%20Table_content:,the%20body:%20Heat%20stroke%20highly%20likely%20%7C)), with Celcius to Fahrenheit conversion and vice versa. The formulation is expected to be valid for US sub-tropical region, but its use for tropical region like Indonesia does not guarantee very accurate results. However, as first-order approximation, this is already sufficient.

2. Administrative regional border data is retrieved from RBI10K_ADMINISTRASI_DESA_20230928 database provided by Badan Informasi Geospasial (BIG).

3. Administrative regional code is taken from [wilayah.id](https://wilayah.id/) based on Kepmendagri No 300.2.2-2138 Tahun 2025.

4. Weather forecast data is taken from the public API of Badan Meteorologi, Klimatologi, dan Geofisika (BMKG) accessed via [Data Prakiraan Cuaca Terbuka](https://data.bmkg.go.id/prakiraan-cuaca/).
