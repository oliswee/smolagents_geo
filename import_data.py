"""Import all 8 data sources into PostgreSQL + PostGIS.

Maps to Iter 0 tasks 0.1-0.6 in the Notebook:
  - SA2 shapefile → sa2_regions (master spatial table)
  - Businesses.csv → businesses
  - Stops.txt → stopcount
  - Catchments/ → schoolcatch
  - Population.csv → popall
  - Income.csv → incomevalue
  - PollingPlaces2019.csv → pollingplaces
  - Playgrounds/ → playgrounds
  - NSW POI API → poi_counts (online, optional)
"""
import sys
sys.path.insert(0, ".")

import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.geometry import MultiPolygon
from geoalchemy2 import Geometry, WKTElement
import time
import requests
import json
from pathlib import Path

from data_warehouse.connection import DatabaseManager

SRID = 4283  # GDA94
DATA = Path("Datasets")
SA2_DIR = Path("SA2_2021_AUST_SHP_GDA2020")

# SA4 regions we focus on (109 SA2 areas)
FOCUS_SA4 = [
    'Sydney - Inner South West',
    'Sydney - Parramatta',
    'Sydney - South West',
]


def create_wkt_element(geom, srid=SRID):
    """Convert shapely geometry to WKTElement for PostGIS import."""
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == 'Polygon':
        geom = MultiPolygon([geom])
    return WKTElement(geom.wkt, srid=srid)


def import_sa2(conn):
    """Import SA2 boundaries — the master spatial table."""
    print("\n[1/8] Importing SA2 boundaries...")

    gdf = gpd.read_file(SA2_DIR)
    # Filter to Greater Sydney
    if 'GCC_NAME21' in gdf.columns:
        gdf = gdf[gdf['GCC_NAME21'] == 'Greater Sydney']

    # Drop unnecessary columns
    keep = ['SA2_CODE21', 'SA2_NAME21', 'SA4_CODE21', 'SA4_NAME21',
            'STE_NAME21', 'geometry']
    gdf = gdf[[c for c in keep if c in gdf.columns]]

    # Create WKTElement geometry
    gdf['geom'] = gdf['geometry'].apply(create_wkt_element)
    gdf = gdf.drop(columns=['geometry'], errors='ignore')

    # Insert via raw connection for Geometry type support
    raw = conn.connection
    with raw.cursor() as cur:
        for _, row in gdf.iterrows():
            cur.execute(
                """INSERT INTO sa2_regions ("SA2_CODE21", "SA2_NAME21", "SA4_CODE21",
                   "SA4_NAME21", "STE_NAME21", geom)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT ("SA2_CODE21") DO NOTHING""",
                (row['SA2_CODE21'], row['SA2_NAME21'], row.get('SA4_CODE21'),
                 row.get('SA4_NAME21'), row.get('STE_NAME21'), row['geom'].desc)
            )
    raw.commit()

    # Verify focus areas
    with raw.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM selected_sa2_regions")
        n = cur.fetchone()[0]
    focus_gdf = gdf[gdf['SA4_NAME21'].isin(FOCUS_SA4)] if 'SA4_NAME21' in gdf.columns else gdf
    print(f"  Total SA2 imported: {len(gdf)}, Focus area (109): {n}")
    return focus_gdf


def import_businesses(conn):
    """Import ABS Business Register data."""
    print("\n[2/8] Importing businesses...")
    df = pd.read_csv(DATA / "Businesses.csv")

    # Sum turnover columns into total_businesses (only if not already present)
    turnover_cols = [c for c in df.columns if c.endswith('_businesses') and c != 'total_businesses']
    if turnover_cols and 'total_businesses' not in df.columns:
        df['total_businesses'] = df[turnover_cols].sum(axis=1)
    if turnover_cols:
        df = df.drop(columns=turnover_cols)

    # Remove 'Currently Unknown' entries
    if 'sa2_name' in df.columns:
        df = df[df['sa2_name'] != 'Currently Unknown']

    # Reorder columns
    cols = ['industry_code', 'industry_name', 'sa2_code', 'sa2_name', 'total_businesses']
    df = df[[c for c in cols if c in df.columns]]

    raw = conn.connection
    # Load valid SA2 codes (FK constraint)
    with raw.cursor() as cur:
        cur.execute('SELECT "SA2_CODE21" FROM sa2_regions')
        valid_codes = {r[0] for r in cur.fetchall()}
    df = df[df['sa2_code'].astype(str).isin(valid_codes)]
    print(f"  After FK filter: {len(df)} business records")

    with raw.cursor() as cur:
        for _, row in df.iterrows():
            cur.execute(
                """INSERT INTO businesses (industry_code, industry_name, sa2_code, sa2_name, total_businesses)
                   VALUES (%s, %s, %s, %s, %s)""",
                (row.get('industry_code'), row.get('industry_name'),
                 str(row.get('sa2_code')), row.get('sa2_name'), int(row['total_businesses']))
            )
    raw.commit()
    print(f"  Imported: {len(df)} business records")


def import_stops(conn):
    """Import GTFS stops with point geometry."""
    print("\n[3/8] Importing transport stops...")
    df = pd.read_csv(DATA / "Stops.txt")

    # Create point geometry
    gdf = gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df.stop_lon, df.stop_lat), crs=f"EPSG:{SRID}"
    )
    gdf['geom'] = gdf['geometry'].apply(lambda g: WKTElement(g.wkt, srid=SRID))

    raw = conn.connection
    with raw.cursor() as cur:
        for _, row in gdf.iterrows():
            cur.execute(
                "INSERT INTO stopcount (stop_id, geom) VALUES (%s, %s)",
                (str(row['stop_id']), row['geom'].desc)
            )
    raw.commit()
    print(f"  Imported: {len(gdf)} stops")


def import_schools(conn):
    """Import school catchment shapefiles."""
    print("\n[4/8] Importing school catchments...")
    catch_dir = DATA / "Catchments" / "catchments"

    all_gdfs = []
    for prefix in ['primary', 'secondary', 'future']:
        shp = catch_dir / f"catchments_{prefix}.shp"
        if shp.exists():
            gdf = gpd.read_file(shp)
            if 'CATCH_TYPE' not in gdf.columns:
                gdf['CATCH_TYPE'] = prefix.upper()
            all_gdfs.append(gdf)

    gdf = gpd.GeoDataFrame(pd.concat(all_gdfs, ignore_index=True))

    # Keep needed columns + geometry → WKTElement
    gdf['geom'] = gdf['geometry'].apply(create_wkt_element)
    gdf['area_km2'] = gdf['geometry'].to_crs(3857).area / 1e6

    keep_cols = ['USE_ID', 'CATCH_TYPE', 'USE_DESC']
    import_cols = [c for c in keep_cols if c in gdf.columns]

    raw = conn.connection
    with raw.cursor() as cur:
        for _, row in gdf.iterrows():
            vals = [row.get(c) for c in import_cols]
            cur.execute(
                f"""INSERT INTO schoolcatch ({", ".join(f'"{c}"' for c in import_cols)}, geom, area_km2)
                    VALUES ({", ".join(["%s"] * len(import_cols))}, %s, %s)""",
                (*vals, row['geom'].desc, row['area_km2'])
            )
    raw.commit()
    print(f"  Imported: {len(gdf)} school catchments")


def import_population(conn):
    """Import ABS Census population by age group."""
    print("\n[5/8] Importing population data...")
    df = pd.read_csv(DATA / "Population.csv")
    df['sa2_code'] = df['sa2_code'].astype(str)
    df = df.drop(columns=['total_people'], errors='ignore')

    raw = conn.connection
    # Load valid SA2 codes for FK filter
    with raw.cursor() as cur:
        cur.execute('SELECT "SA2_CODE21" FROM sa2_regions')
        valid_codes = {r[0] for r in cur.fetchall()}
    df = df[df['sa2_code'].isin(valid_codes)]
    print(f"  After FK filter: {len(df)} population records")
    age_cols = [c for c in df.columns if c != 'sa2_code' and c != 'sa2_name']
    with raw.cursor() as cur:
        for _, row in df.iterrows():
            vals = [row.get(c, 0) for c in age_cols]
            cur.execute(
                f"""INSERT INTO popall (sa2_code, sa2_name, {", ".join(f'"{c}"' for c in age_cols)})
                    VALUES (%s, %s, {", ".join(["%s"] * len(age_cols))})
                    ON CONFLICT (sa2_code) DO NOTHING""",
                (row['sa2_code'], row.get('sa2_name', ''), *vals)
            )
    raw.commit()
    print(f"  Imported: {len(df)} SA2 areas")


def import_income(conn):
    """Import ATO income statistics with missing value handling."""
    print("\n[6/8] Importing income data...")
    df = pd.read_csv(DATA / "Income.csv")
    df['sa2_code21'] = df['sa2_code21'].astype(str)

    # Clean median_income: replace 'np' with NaN
    if 'median_income' in df.columns:
        df['median_income'] = pd.to_numeric(
            df['median_income'].replace('np', np.nan), errors='coerce'
        )

    # FK filter
    raw = conn.connection
    with raw.cursor() as cur:
        cur.execute('SELECT "SA2_CODE21" FROM sa2_regions')
        valid_codes = {r[0] for r in cur.fetchall()}
    df = df[df['sa2_code21'].isin(valid_codes)]
    print(f"  After FK filter: {len(df)} income records")
    with raw.cursor() as cur:
        for _, row in df.iterrows():
            cur.execute(
                """INSERT INTO incomevalue (sa2_code21, sa2_name, earners, median_age, median_income, mean_income)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (sa2_code21) DO NOTHING""",
                (row['sa2_code21'], row.get('sa2_name', ''),
                 str(row.get('earners', '')), str(row.get('median_age', '')),
                 float(row['median_income']) if pd.notna(row.get('median_income')) else None,
                 str(row.get('mean_income', '')))
            )
    raw.commit()
    print(f"  Imported: {len(df)} SA2 areas")


def import_polling_places(conn):
    """Import AEC polling places with point geometry."""
    print("\n[7/8] Importing polling places...")
    fp = DATA / "PollingPlaces2019.csv"
    if not fp.exists():
        print("  PollingPlaces2019.csv not found — skipping")
        return

    df = pd.read_csv(fp)
    # Expect columns: PollingPlace, Address, Latitude, Longitude
    lat_col = next((c for c in df.columns if 'lat' in c.lower()), None)
    lon_col = next((c for c in df.columns if 'lon' in c.lower()), None)
    name_col = next((c for c in df.columns if 'name' in c.lower() or 'place' in c.lower()), None)
    addr_col = next((c for c in df.columns if 'addr' in c.lower()), None)

    if lat_col and lon_col:
        gdf = gpd.GeoDataFrame(
            df, geometry=gpd.points_from_xy(df[lon_col], df[lat_col]), crs=f"EPSG:{SRID}"
        )
        gdf['geom'] = gdf['geometry'].apply(lambda g: WKTElement(g.wkt, srid=SRID))

        raw = conn.connection
        with raw.cursor() as cur:
            for _, row in gdf.iterrows():
                cur.execute(
                    "INSERT INTO pollingplaces (place_name, address, geom) VALUES (%s, %s, %s)",
                    (str(row.get(name_col, '')) if name_col else '',
                     str(row.get(addr_col, '')) if addr_col else '',
                     row['geom'].desc)
                )
        raw.commit()
        print(f"  Imported: {len(gdf)} polling places")
    else:
        print("  Could not find lat/lon columns — skipping")


def import_playgrounds(conn):
    """Import City of Sydney playgrounds & fitness stations."""
    print("\n[8/8] Importing playgrounds...")
    pg_dir = DATA / "Playgrounds"
    if not pg_dir.exists():
        print("  Playgrounds directory not found — skipping")
        return

    total = 0
    raw = conn.connection

    # Try shapefile first
    shp_files = list(pg_dir.glob("*.shp"))
    for shp_f in shp_files:
        gdf = gpd.read_file(shp_f)
        gdf = gdf.to_crs(f"EPSG:{SRID}")
        gdf['geom'] = gdf['geometry'].apply(lambda g: WKTElement(g.wkt, srid=SRID))

        # Map columns: Name → facility_name, Type → facility_type
        name_col = next((c for c in gdf.columns if c.lower() in ('name', 'facility', 'site', 'location')), None)
        type_col = next((c for c in gdf.columns if c.lower() in ('type', 'category', 'class')), None)

        with raw.cursor() as cur:
            for _, row in gdf.iterrows():
                fname = str(row[name_col]) if name_col else str(shp_f.stem)
                ftype = str(row[type_col]).lower() if type_col else 'playground'
                cur.execute(
                    "INSERT INTO playgrounds (facility_name, facility_type, geom) VALUES (%s, %s, %s)",
                    (fname, ftype, row['geom'].desc)
                )
        raw.commit()
        total += len(gdf)
        print(f"  Shapefile {shp_f.name}: {len(gdf)} features")

    # Try CSV
    for csv_f in pg_dir.glob("*.csv"):
        df = pd.read_csv(csv_f)
        lat_col = next((c for c in df.columns if 'lat' in c.lower()), None)
        lon_col = next((c for c in df.columns if 'lon' in c.lower()), None)
        name_col = next((c for c in df.columns if 'name' in c.lower()), None)
        if lat_col and lon_col:
            gdf = gpd.GeoDataFrame(
                df, geometry=gpd.points_from_xy(df[lon_col], df[lat_col]), crs=f"EPSG:{SRID}"
            )
            gdf['geom'] = gdf['geometry'].apply(lambda g: WKTElement(g.wkt, srid=SRID))
            with raw.cursor() as cur:
                for _, row in gdf.iterrows():
                    cur.execute(
                        "INSERT INTO playgrounds (facility_name, facility_type, geom) VALUES (%s, %s, %s)",
                        (str(row.get(name_col, '')) if name_col else str(csv_f.stem),
                         'playground', row['geom'].desc)
                    )
            raw.commit()
            total += len(gdf)
    print(f"  Imported: {total} playground/fitness sites")


def import_poi_counts(conn, sa2_gdf=None):
    """Fetch POI counts from NSW POI API for each SA2 (online, optional)."""
    print("\n[Bonus] Importing POI counts from NSW API...")
    API_URL = "https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_POI/MapServer/0/query"

    # Get focus areas from DB
    raw = conn.connection
    with raw.cursor() as cur:
        cur.execute('SELECT "SA2_CODE21", "SA2_NAME21", "SA4_NAME21" FROM selected_sa2_regions')
        areas = cur.fetchall()

    if not areas:
        print("  No areas in selected_sa2_regions — skipping")
        return

    total = 0
    for code, name, sa4 in areas:
        # Get centroid bounding box
        with raw.cursor() as cur:
            cur.execute(
                'SELECT ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom) '
                'FROM sa2_regions WHERE "SA2_CODE21" = %s', (code,)
            )
            bbox = cur.fetchone()

        if not bbox:
            continue

        params = {
            "where": "1=1",
            "geometry": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": SRID, "outSR": SRID,
            "outFields": "*", "f": "json"
        }

        try:
            r = requests.get(API_URL, params=params, timeout=20)
            r.raise_for_status()
            count = len(r.json().get("features", []))
        except Exception as e:
            count = 0

        with raw.cursor() as cur:
            cur.execute(
                "INSERT INTO poi_counts (sa2_code, sa2_name, sa4_name, poi_count) VALUES (%s, %s, %s, %s)",
                (code, name, sa4, count)
            )
        raw.commit()
        total += count
        if total % 5000 == 0:
            print(f"  Progress: ~{total} POIs fetched...")
        time.sleep(0.15)  # Rate limit

    print(f"  Imported POI counts for {len(areas)} areas, ~{total} total POIs")


# ================================================================
# Main
# ================================================================
if __name__ == "__main__":
    config = DatabaseManager.get_config_from_credentials()
    db = DatabaseManager(config)
    engine, conn = db.connect()

    # Import all sources
    import_sa2(conn)
    import_businesses(conn)
    import_stops(conn)
    import_schools(conn)
    import_population(conn)
    import_income(conn)
    import_polling_places(conn)
    import_playgrounds(conn)

    # POI from API (optional — can be very slow, ~30 min for 109 areas)
    print("\n" + "=" * 60)
    resp = input("Import POI counts from NSW API? This takes ~30 min. (y/n): ")
    if resp.lower().startswith('y'):
        import_poi_counts(conn)

    # Verify row counts
    print("\n" + "=" * 60)
    print("Data import summary:")
    with conn.connection.cursor() as cur:
        for table in ['sa2_regions', 'businesses', 'stopcount', 'schoolcatch',
                       'popall', 'incomevalue', 'pollingplaces', 'playgrounds',
                       'poi_counts']:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            n = cur.fetchone()[0]
            print(f"  {table:25s} {n:>8,d} rows")

    conn.close()
    print("\n✅ Data import complete!")
