# Jakarta Heat Risk App

This repository contains the source code to build a Python-based web application with Flask and Plotly which is intended to show information about heat index and risk for every single ward (kelurahan) in the Jakarta province. The 3-hourly weather forecast data are available for each ward and are provided by Badan Meteorologi, Klimatologi, dan Geofisika (BMKG) through public API described in [Data Terbuka BMKG](https://data.bmkg.go.id/prakiraan-cuaca/).

🎥 [**YOU CAN ACCESS THE LIVE DEMO HERE**](https://heat-risk.vercel.app) 🎥

⚠️ **IMPORTANT!** ⚠️  
- The app requires MySQL database and uses the live Jakarta time to choose the nearest available forecast snapshot. Missing database environment variables or an unreachable MySQL server will cause the app to raise an error.
- The app does not fetch live data during user interaction, which mainstream weather apps usually do, but depends on a refresh job to update the cloud database from the live API.

![Jakarta Heat Risk App](/figures/main_page.png)


## Tools Used

### Backend
- Pandas
- MySQL
- Plotly
- Flask

### Frontend
- HTML
- React JS

## Running

Install the dependencies first:

```bash
pip install -r requirements.txt
```

Create a local `.env` file in the project root, or export the environment variables listed in the Environment Variables section below.

If the weather table and runtime metadata have not been populated yet, run the BMKG refresh pipeline once:

```bash
python fetch/fetch_weather_data.py
```

This should take around 4 to 5 minutes because the script fetches ward-level forecasts one by one with a polite delay to stay under BMKG's rate limit.

Start the Flask app:

```bash
python app.py
```

By default, Flask serves the app locally at [http://127.0.0.1:5000](http://127.0.0.1:5000). The React frontend is loaded from `templates/index.html` and `assets/app.js`, while the backend API is served from `app.py`.

If you want to rebuild the ward boundary files with [fetch/fetch_boundary_data.py](fetch/fetch_boundary_data.py), download the required `.gdb` source from [BIG](https://geoservices.big.go.id/portal/apps/webappviewer/index.html?id=cb58db080712468cb4bfd408dbde3d70) first.

## Environment Variables

The app and fetch pipeline require a MySQL database connection. These variables can be provided through a local `.env` file or through your deployment platform.

| Variable | Description |
| --- | --- |
| `DB_HOST` | MySQL host |
| `DB_PORT` | MySQL port |
| `DB_USER` | MySQL user name. |
| `DB_PASSWORD` | MySQL password. |
| `DB_NAME` | MySQL database name used by the app and fetch scripts. |


## Content

```text
.
├── api/
│   └── cron_refresh.py                  # Vercel cron endpoint
├── assets/
│   ├── app.js                           
│   ├── style.css                        
│   └── *.svg                            # Weather and UI icons
├── fetch/
│   ├── build_jakarta_preference.py      # Builds ward reference codes from wilayah.id
│   ├── fetch_boundary_data.py           # Rebuilds Jakarta ward boundary GeoJSON files
│   └── fetch_weather_data.py            # Fetches BMKG forecasts and writes them to MySQL
├── figures/
│   └── ...                              
├── src/
│   ├── constant.py                      # Shared app constants and display mappings
│   ├── db.py                            # Database and Jakarta-time helpers
│   ├── helpers.py                       # Data loading, metadata, search, and forecast helpers
│   └── plotting.py                      # Plot and map-color preparation helpers
├── tables/
│   ├── jakarta_boundary_simplified.geojson # Ward boundary GeoJSON
│   └── jakarta_boundary_simplified.geojson.gz # Compressed ward boundary GeoJSON
├── templates/
│   └── index.html                       
├── app.py                               
├── jakarta_reference.csv                # Ward reference table used by the fetch pipeline
├── requirements.txt                    
└── vercel.json                          # Vercel cron schedule configuration
```

Note that the only time-dependent data in this project is the BMKG weather data, so the boundary polygon and region code will always be static values.

The weather fetch pipeline uploads directly to a cloud MySQL database. Each BMKG refresh run takes about 4 minutes due to the polite delay of 1.01 seconds for each of 261 wards in Jakarta to respect BMKG request limit of 60 requests / minute / IP.


## Author's Remarks

This project was inspired by the tropical condition of Jakarta. Average daytime temperature for downtown Jakarta of about $32\degree$ Celcius ([measurements from 1991 to 2000](https://web.archive.org/web/20231019195817/https://www.nodc.noaa.gov/archive/arc0216/0253808/1.1/data/0-data/Region-5-WMO-Normals-9120/Indonesia/CSV/StasiunMeteorologiKemayoran_96745.csv)) and at a fairly consistent value throughout the year makes its population susceptible to some level of heat risks. This is worsen by the climate change that is getting severe for the past several years, with multiple heat waves reported across the globe (see [here](https://wmo.int/news/media-centre/rising-temperatures-and-extreme-weather-hit-asia-hard) for example). Based on the [U.S. National Weather Service](https://www.weather.gov/ama/heatindex#:~:text=Table_title:%20What%20is%20the%20heat%20index?%20Table_content:,the%20body:%20Heat%20stroke%20highly%20likely%20%7C), temperatures just above $32\degree$ Celcius can start to induce some negative effects on human body such as heat exhaustion, heat cramps, and even heat stroke from prolonged exposure. With many Jakartans working outside, for example as *ojol*, street vendors, or just being stuck in traffic under the scorching sunlight, the risk of these complications may be even greater than realized. 

The use of generative AI includes: Github Copilot to help in code syntax and identifying bugs and errors. Outside of those, including problem formulation and framework of thinking, code logical reasoning and writing, from database management to web development using Flask, all is done mostly by the author.

## Data Sources

1. Heat index is computed using the regression formula from the US National Weather Service ([see here](https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml) and [here](https://www.weather.gov/ama/heatindex#:~:text=Table_title:%20What%20is%20the%20heat%20index?%20Table_content:,the%20body:%20Heat%20stroke%20highly%20likely%20%7C)), with Celcius to Fahrenheit conversion and vice versa. The formulation is expected to be valid for US sub-tropical region, but its use for tropical region like Indonesia does not guarantee very accurate results. However, as first-order approximation, this is already sufficient.

2. Administrative regional border data is retrieved from RBI10K_ADMINISTRASI_DESA_20230928 database provided by Badan Informasi Geospasial (BIG).

3. Administrative regional code is taken from [wilayah.id](https://wilayah.id/) based on Kepmendagri No 300.2.2-2138 Tahun 2025.

4. Weather forecast data is taken from the public API of Badan Meteorologi, Klimatologi, dan Geofisika (BMKG) accessed via [Data Prakiraan Cuaca Terbuka](https://data.bmkg.go.id/prakiraan-cuaca/).
