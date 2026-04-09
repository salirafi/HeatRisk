#!/usr/bin/env python3
"""
Build and save Jakarta ward-level (desa/kelurahan) boundary data from BIG RBI geodatabase.
Also export the ward adm4 codes into MySQL for LEFT JOINs used by the choropleth map.
"""

from __future__ import annotations

from pathlib import Path

import fiona
import geopandas as gpd
import pandas as pd
from sqlalchemy import String, text

import sys
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.db import get_mysql_engine


GDB_PATH = BASE_DIR / "tables" / "RBI10K_ADMINISTRASI_DESA_20230928.gdb"
OUTPUT_GEOJSON = BASE_DIR / "tables" / "jakarta_boundary_simplified.geojson"

# layer's name can be checked with the following code: print(fiona.listlayers(gdb_path)); see list_gdb_layers() function below
GDB_LAYER = ["ADMINISTRASI_AR_DESAKEL"]

BOUNDARY_INDEX_TABLE = "map_boundary_index"


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    # remove dots to avoid mismatches
    # strip whitespace and convert to uppercase for case-insensitive matching
    return str(value).strip().upper().replace(".", "")


def list_gdb_layers(gdb_path: Path) -> list[str]:
    return fiona.listlayers(str(gdb_path)) # return available layers inside the GDB.


def resolve_layer_name(gdb_path: Path) -> str:
    layers = list_gdb_layers(gdb_path) 

    for candidate in GDB_LAYER:
        if candidate in layers:
            return candidate

    for layer in layers:
        layer_upper = layer.upper()
        if "DESA" in layer_upper or "KEL" in layer_upper:
            return layer

    raise ValueError(
        f"Unable to locate a ward-level boundary layer in {gdb_path}. Available layers: {layers}"
    )




# this is at desa/kelurahan level, so the code is the most granular one (adm4)
def load_boundary_layer(gdb_path: Path, layer: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(str(gdb_path), layer=layer)
    columns = list(gdf.columns)

    # keep only useful columns and the geometry
    gdf = gdf[["KDEPUM", "WADMKD", "WADMKC", "WADMKK", "WADMPR", "geometry"]].copy()
    gdf = gdf.rename(
        columns={
            "KDEPUM": "adm4",
            "WADMKD": "ward_name",
            "WADMKC": "district_name",
            "WADMKK": "city_name",
            "WADMPR": "province_name",
        }
    )

    for col in ["adm4", "ward_name", "district_name", "city_name", "province_name"]:
        gdf[col] = gdf[col].astype(str).str.strip()

    gdf["province_clean"] = gdf["province_name"].apply(clean_text)

    return gdf

# filters to only Jakarta's wards' boundaries
def filter_jakarta_boundaries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return gdf[gdf["province_clean"] == "DKI JAKARTA"].copy()


# function to build the boundary table and export as GeoJSON
def build_and_export_geojson(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    export_gdf = gdf.copy()
    export_gdf = export_gdf.to_crs(epsg=4326)
    gdf["geometry"] = gdf["geometry"].simplify(tolerance=0.0005,preserve_topology=True) # save a simplified version of the geometry for faster loading
    export_gdf["geometry"] = export_gdf.geometry.make_valid() # repair invalid geometries to be valid

    # look https://geopandas.org/en/stable/docs/user_guide/missing_empty.html for differences between empty and missing
    export_gdf = export_gdf[export_gdf.geometry.notna()]
    export_gdf = export_gdf[~export_gdf.geometry.is_empty]

    export_gdf = export_gdf.dropna(subset=["adm4"])
    export_gdf = export_gdf[export_gdf["adm4"] != ""].copy()
    export_gdf = export_gdf.drop_duplicates(subset=["adm4"]).reset_index(drop=True)  # keep only distinct region code values
    export_gdf = export_gdf[
        ["adm4", "geometry"] # keep only codes and geometry 
    ].copy()

    OUTPUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    export_gdf.to_file(OUTPUT_GEOJSON, driver="GeoJSON")
    return export_gdf

# create boundary index to merge with weather table for choropleth plotting
def export_boundary_index_to_mysql(gdf: gpd.GeoDataFrame, table_name: str) -> pd.DataFrame:
    index_df = (
        gdf[["adm4"]]
        .dropna(subset=["adm4"])
        .query("adm4 != ''")
        .drop_duplicates(subset=["adm4"])
        .sort_values("adm4")
        .reset_index(drop=True)
    )

    engine = get_mysql_engine()
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        conn.execute(text(f"""
            CREATE TABLE {table_name} (
                adm4 VARCHAR(32) NOT NULL,
                PRIMARY KEY (adm4)
            )
        """))

    index_df.to_sql(
        table_name,
        engine,
        if_exists="append",
        index=False,
        dtype={"adm4": String(32)},
    )

    return index_df


def main() -> None:
    layers = list_gdb_layers(GDB_PATH)
    layer = resolve_layer_name(GDB_PATH)
    gdf = load_boundary_layer(GDB_PATH, layer)
    gdf_jakarta = filter_jakarta_boundaries(gdf)
    exported_gdf = build_and_export_geojson(gdf_jakarta)
    index_df = export_boundary_index_to_mysql(exported_gdf, BOUNDARY_INDEX_TABLE)

    print("")
    print("=== Available GDB layers ===")
    print(layers)
    print("")
    print("=== Selected layer ===")
    print(layer)
    print("")
    print("=== Export summary ===")
    print(f"Ward polygons exported: {len(exported_gdf)}")
    print(f"MySQL rows exported to {BOUNDARY_INDEX_TABLE}: {len(index_df)}")
    print(f"GeoJSON written to: {OUTPUT_GEOJSON}")
    print("")
    print("=== Fetching done. ===")


if __name__ == "__main__":
    main()
