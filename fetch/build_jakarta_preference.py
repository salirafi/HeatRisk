#!/usr/bin/env python3
"""
Creating jakarta_reference.csv containing region code for every ward in Jakarta.
Get data from https://wilayah.id/api
"""

import time
import requests
import pandas as pd
from pathlib import Path

BASE_URL = "https://wilayah.id/api"

BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = BASE_DIR / "jakarta_reference.csv"

# Mainland Jakarta only for this project 
# codes are pre-written: 31.xx
JAKARTA_MAINLAND_REGENCIES = {
    "31.71": "Kota Adm. Jakarta Pusat",
    "31.72": "Kota Adm. Jakarta Utara",
    "31.73": "Kota Adm. Jakarta Barat",
    "31.74": "Kota Adm. Jakarta Selatan",
    "31.75": "Kota Adm. Jakarta Timur",
}

def get_json(url: str) -> dict:
    resp = requests.get(url, \
                        timeout=30) # set a timeout to avoid hanging indefinitely if the server is not responding
    resp.raise_for_status()  # raise Error if the request failed
    return resp.json()

# fetch districts (kecamatan-level) for a given regency code, return a list of dicts with keys "code" and "name"
def fetch_districts(regency_code: str) -> list[dict]:
    url = f"{BASE_URL}/districts/{regency_code}.json" # districts -> kecamatan
    payload = get_json(url)
    return payload.get("data", [])

# fetch villages (desa/kelurahan-level) for a given district code, return a list of dicts with keys "code" and "name"
def fetch_villages(district_code: str) -> list[dict]:
    url = f"{BASE_URL}/villages/{district_code}.json" # villages -> desa/kelurahan
    payload = get_json(url)
    return payload.get("data", [])

# build the reference DataFrame by fetching data from wilayah.id for all regencies, districts, and villages in mainland Jakarta
def build_reference() -> pd.DataFrame:
    rows = []

    # loop through each regency in mainland Jakarta, fetch its districts, 
    # then for each district fetch its villages, and construct rows for the DataFrame with the appropriate codes and names
    for regency_code, regency_name in JAKARTA_MAINLAND_REGENCIES.items():
        print(f"Fetching districts for {regency_name} ({regency_code})")
        districts = fetch_districts(regency_code) # shape is list of dicts with keys "code" and "name"

        for district in districts:
            district_code = district["code"]
            district_name = district["name"]

            print(f"  Fetching villages for {district_name} ({district_code})")
            villages = fetch_villages(district_code) # shape is list of dicts with keys "code" and "name"

            for village in villages:
                rows.append(
                    {
                        "adm4": village["code"],
                        "desa_kelurahan": village["name"],
                        "kecamatan_code": district_code,
                        "kecamatan": district_name,
                        "kotkab_code": regency_code,
                        "kota_kabupaten": regency_name,
                        "provinsi_code": "31",
                        "provinsi": "DKI Jakarta",
                    }
                )

            # small pause to be polite
            time.sleep(0.2)

    df = pd.DataFrame(rows)

    if df.empty:
        raise ValueError("No rows were fetched from wilayah.id")

    # remove duplicates just in case, sort by codes for better readability, and reset index to be clean and sequential
    df = (
        df.drop_duplicates(subset=["adm4"])
          .sort_values(["kotkab_code", "kecamatan_code", "adm4"])
          .reset_index(drop=True)
    )

    return df

def main():
    df = build_reference()
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print("\nSaved file:", OUTPUT_FILE)
    print("Total rows:", len(df))
    print("\nPreview:")
    print(df.head(20).to_string(index=False))
if __name__ == "__main__":
    main()
