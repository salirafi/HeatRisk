#!/usr/bin/env python3
"""
Build and save Jakarta ward (kelurahan) boundary data from RBI geodatabase from Badan Informasi Geospasial.
Saving is done to SQLite.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import fiona
import geopandas as gpd
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "tables" / "heat_risk.db"

GDB_PATH = BASE_DIR / "fetch" / "RBI10K_ADMINISTRASI_DESA_20230928.gdb"
OUTPUT_TABLE = "ward_boundary_table"
OUTPUT_BOUNDARY_INDEX_TABLE = "map_boundary_index"
OUTPUT_GEOJSON = BASE_DIR / "tables" / "jakarta_boundary_simplified.geojson"
# layer's name can be checked with the following code: print(fiona.listlayers(gdb_path)); see list_gdb_layers() function below
GDB_LAYER = "ADMINISTRASI_AR_DESAKEL"

# the name for Jakarta in the GDB is "Kota Adm. Jakarta xxx"
JAKARTA_CITIES = {
    "KOTA ADM JAKARTA PUSAT",
    "KOTA ADM JAKARTA UTARA",
    "KOTA ADM JAKARTA BARAT",
    "KOTA ADM JAKARTA SELATAN",
    "KOTA ADM JAKARTA TIMUR",
}

def clean_text(value: object) -> str | None:
    """Normalize text for safer matching across files."""
    if value is None:
        return None
    # remove dots to avoid mismatches
    # strip whitespace and convert to uppercase for case-insensitive matching
    return str(value).strip().upper().replace(".", "")

def list_gdb_layers(gdb_path: Path) -> list[str]:
    """Return available layers inside the GDB."""
    return fiona.listlayers(str(gdb_path))

# this is at desa/kelurahan level, so the code is the most granular one (adm4)
def load_boundary_layer(gdb_path: Path, layer: str) -> gpd.GeoDataFrame:
    """Load the desa/kelurahan boundary layer and keep only needed columns"""
    gdf = gpd.read_file(str(gdb_path), layer=layer)

    # keep only useful columns and the geometry
    gdf = gdf[
        ["NAMOBJ", "KDEPUM", "WADMKD", "WADMKC", "WADMKK", "WADMPR", "geometry",
        ]
    ].copy()

    for col in ["NAMOBJ", "WADMKD", "WADMKC", "WADMKK", "WADMPR", "KDEPUM"]:
        gdf[col] = gdf[col].astype(str).str.strip() # ensure all are strings and remove leading/trailing whitespace

    # create cleaned versions of the relevant columns for matching purposes
    gdf["desa_clean"] = gdf["WADMKD"].apply(clean_text)
    gdf["kecamatan_clean"] = gdf["WADMKC"].apply(clean_text)
    gdf["kotkab_clean"] = gdf["WADMKK"].apply(clean_text)
    gdf["provinsi_clean"] = gdf["WADMPR"].apply(clean_text)
    gdf["kdepum_clean"] = gdf["KDEPUM"].astype(str).str.strip()

    return gdf

# filters to only Jakarta's wards' boundaries
def filter_jakarta_boundaries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep only DKI Jakarta administrative areas."""
    return gdf[
        (gdf["provinsi_clean"] == "DKI JAKARTA")
        & (gdf["kotkab_clean"].isin(JAKARTA_CITIES))
    ].copy()

# function to build the boundary table and export as GeoJSON
def build_and_export_table(gdf: gpd.GeoDataFrame) -> pd.DataFrame:

    gdf = gdf.copy()
    gdf = gdf.to_crs(epsg=4326)
    gdf["geometry"] = gdf["geometry"].simplify(tolerance=0.001,preserve_topology=True) # save a simplified version of the geometry for faster loading
    gdf["geometry"] = gdf.geometry.make_valid() # repair invalid geometries to be valid

    # look https://geopandas.org/en/stable/docs/user_guide/missing_empty.html for differences between empty and missing
    gdf = gdf[gdf.geometry.notna()] # drop missing geometries
    gdf = gdf[~gdf.geometry.is_empty] # drop empty geometries

    gdf["KDEPUM"] = gdf["KDEPUM"].astype(str).str.strip()
    gdf = gdf.drop_duplicates(subset=["KDEPUM"]).reset_index(drop=True)  # keep only distinct region code values

    # keep only the relevant columns (omitting 'NAMOBJ' and 'geometry' columns)
    gdf = gdf[
        [
            "KDEPUM",
            "geometry",
        ]
    ].copy()

    # rename columns to match the name formatting in BMKG data
    gdf = gdf.rename(
        columns={"KDEPUM": "adm4",}
        )  

    OUTPUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUTPUT_GEOJSON, driver="GeoJSON") # save as GeoJSON

    # Convert Jakarta boundaries into a SQLite-friendly table with WKB geometry
    gdf["geometry"] = gdf.geometry.to_wkb() # convert geometry to WKB format for easier storage in SQLite; changed to pd.DataFrame

    return gdf

# create boundary index to merge with weather table for choropleth plotting
# without it, the indexing of the color to the corresponding region will be incorrect
# this is separate from ward_boundary_table_simplified (that contains the geometry data) to save memory usage in the web app
def build_boundary_index_table(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Build a tiny boundary index table used for SQL LEFT JOINs in the app
    Contains one row per adm4 code
    """
    df = gdf.copy()

    df["KDEPUM"] = df["KDEPUM"].astype(str).str.strip()

    index_df = (
        df[["KDEPUM"]]
        .drop_duplicates(subset=["KDEPUM"])
        .rename(columns={"KDEPUM": "adm4"})
        .sort_values("adm4")
        .reset_index(drop=True)
    )

    return index_df

def save_boundary_table(df: pd.DataFrame, db_path: Path, table_name: str) -> None:
    """Write the boundary table into SQLite, replacing any older version"""
    with sqlite3.connect(db_path) as conn:
        
        # should be replace not append, since we want to overwrite any old version of the table
        df.to_sql(table_name, conn, if_exists="replace", index=False)

def save_boundary_index_table(df: pd.DataFrame, db_path: Path, table_name: str) -> None:
    """Write the boundary index table into SQLite and add an index on adm4"""
    with sqlite3.connect(db_path) as conn:
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_adm4 ON {table_name}(adm4)")
        conn.commit()

def main() -> None:

    layers = list_gdb_layers(GDB_PATH)
    gdf = load_boundary_layer(GDB_PATH, GDB_LAYER)
    gdf_jakarta = filter_jakarta_boundaries(gdf)
    boundary_df = build_and_export_table(gdf_jakarta)
    boundary_index_df = build_boundary_index_table(gdf_jakarta)

    save_boundary_table(boundary_df, DB_PATH, OUTPUT_TABLE + "_simplified")
    save_boundary_index_table(boundary_index_df, DB_PATH, OUTPUT_BOUNDARY_INDEX_TABLE)

    print("")
    print("")
    print("=== Available GDB layers ===")
    print(layers)
    print("")

    print("=== Fetching done. ===")

if __name__ == "__main__":
    main()
