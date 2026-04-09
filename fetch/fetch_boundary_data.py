#!/usr/bin/env python3
"""
Build and save Jakarta city-level (kabupaten/kota) boundary data from RBI geodatabase from Badan Informasi Geospasial.
Saving is done to GeoJSON for "Regional Info" page.
"""

from __future__ import annotations

from pathlib import Path

import fiona
import geopandas as gpd
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]

GDB_PATH = BASE_DIR / "tables" / "RBI50K_ADMINISTRASI_KABKOTA_20230907.gdb"
OUTPUT_GEOJSON = BASE_DIR / "tables" / "jakarta_city_boundary_simplified.geojson"
# layer's name can be checked with the following code: print(fiona.listlayers(gdb_path)); see list_gdb_layers() function below
GDB_LAYER_CANDIDATES = [
    "ADMINISTRASI_AR_KABKOTA",
    "ADMINISTRASI_AR_KAB_KOTA",
]

# the name for Jakarta in the GDB is "Kota Adm. Jakarta xxx"
JAKARTA_CITIES = {
    "KOTA ADM JAKARTA PUSAT",
    "KOTA ADM JAKARTA UTARA",
    "KOTA ADM JAKARTA BARAT",
    "KOTA ADM JAKARTA SELATAN",
    "KOTA ADM JAKARTA TIMUR",
}

def clean_text(value: object) -> str | None:
    if value is None:
        return None
    # remove dots to avoid mismatches
    # strip whitespace and convert to uppercase for case-insensitive matching
    return str(value).strip().upper().replace(".", "")


def short_city_name(name: object) -> str:
    cleaned = clean_text(name)
    if cleaned is None:
        return ""

    prefixes = [
        "KOTA ADM ",
        "KOTA ADMINISTRASI ",
        "KABUPATEN ADM ",
        "KABUPATEN ADMINISTRASI ",
    ]
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break

    return cleaned.title()

def list_gdb_layers(gdb_path: Path) -> list[str]:
    return fiona.listlayers(str(gdb_path))


def resolve_layer_name(gdb_path: Path) -> str:
    layers = list_gdb_layers(gdb_path)

    for candidate in GDB_LAYER_CANDIDATES:
        if candidate in layers:
            return candidate

    for layer in layers:
        if "KAB" in layer.upper() and "KOTA" in layer.upper():
            return layer

    raise ValueError(
        f"Unable to locate a kabupaten/kota layer in {gdb_path}. Available layers: {layers}"
    )


# pick the first existing column from the list of candidates to handle variations in column naming across different GDB versions
def pick_first_existing_column(columns: list[str], candidates: list[str], label: str) -> str:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    raise ValueError(f"Could not find a {label} column. Available columns: {columns}")

# load the city boundary layer and keep only needed columns
# this is at kabupaten/kota level, so one polygon corresponds to one Jakarta city
def load_boundary_layer(gdb_path: Path, layer: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(str(gdb_path), layer=layer)

    city_col = pick_first_existing_column(
        list(gdf.columns),
        ["WADMKK", "NAMOBJ", "WADMKD"],
        "city-name",
    )
    province_col = pick_first_existing_column(
        list(gdf.columns),
        ["WADMPR"],
        "province-name",
    )

    # keep only useful columns and the geometry
    gdf = gdf[[city_col, province_col, "geometry"]].copy()
    gdf = gdf.rename(columns={city_col: "city_full_name", province_col: "province_name"})

    for col in ["city_full_name", "province_name"]:
        gdf[col] = gdf[col].astype(str).str.strip() # ensure all are strings and remove leading/trailing whitespace

    # create cleaned versions of the relevant columns for matching purposes
    gdf["kotkab_clean"] = gdf["city_full_name"].apply(clean_text)
    gdf["provinsi_clean"] = gdf["province_name"].apply(clean_text)
    gdf["city_name"] = gdf["city_full_name"].apply(short_city_name)

    return gdf

# filters to only Jakarta's city boundaries
def filter_jakarta_boundaries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return gdf[
        (gdf["provinsi_clean"] == "DKI JAKARTA")
        & (gdf["kotkab_clean"].isin(JAKARTA_CITIES))
    ].copy()

# function to build the boundary table and export as GeoJSON
def build_and_export_table(gdf: gpd.GeoDataFrame) -> pd.DataFrame:

    gdf = gdf.copy()
    gdf = gdf.to_crs(epsg=4326)
    # gdf["geometry"] = gdf["geometry"].simplify(tolerance=0.001,preserve_topology=True) # save a simplified version of the geometry for faster loading
    gdf["geometry"] = gdf.geometry.make_valid() # repair invalid geometries to be valid

    # look https://geopandas.org/en/stable/docs/user_guide/missing_empty.html for differences between empty and missing
    gdf = gdf[gdf.geometry.notna()] # drop missing geometries
    gdf = gdf[~gdf.geometry.is_empty] # drop empty geometries

    gdf["city_name"] = gdf["city_name"].astype(str).str.strip()
    gdf["city_full_name"] = gdf["city_full_name"].astype(str).str.strip()
    gdf = gdf[gdf["city_name"] != ""].copy()
    gdf = gdf.drop_duplicates(subset=["city_name"]).reset_index(drop=True)  # keep only one simplified polygon per city

    # keep only the relevant columns and geometry for the Regional Info page
    gdf = gdf[
        [
            "city_name",
            "city_full_name",
            "geometry",
        ]
    ].copy()

    OUTPUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUTPUT_GEOJSON, driver="GeoJSON") # save as GeoJSON

    return gdf

def main() -> None:

    layers = list_gdb_layers(GDB_PATH)
    layer = resolve_layer_name(GDB_PATH)
    gdf = load_boundary_layer(GDB_PATH, layer)
    gdf_jakarta = filter_jakarta_boundaries(gdf)
    build_and_export_table(gdf_jakarta)

    print("")
    print("")
    print("=== Available GDB layers ===")
    print(layers)
    print("")
    print("=== Selected layer ===")
    print(layer)
    print("")

    print("=== Fetching done. ===")

if __name__ == "__main__":
    main()
