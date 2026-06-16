"""Skill 2: Spatial Accessibility Analyzer.

Queries PostGIS for facility counts within a radius of an area centroid.
Supports multiple facility types across all data tables.
"""
from smolagents import tool


FACILITY_TABLE_MAP = {
    "clinic": {
        "table": "poi_counts",
        "description": "诊所/医疗设施",
        "geometry_source": "sa2_regions",  # POI counts are pre-aggregated
    },
    "school": {
        "table": "schoolcatch",
        "description": "学校",
        "geom_column": "geom",
    },
    "transport": {
        "table": "stopcount",
        "description": "公交站点",
        "geom_column": "geom",
    },
    "playground": {
        "table": "playgrounds",
        "description": "游乐场/健身设施",
        "geom_column": "geom",
    },
    "community": {
        "table": "pollingplaces",
        "description": "社区公共设施(投票站等)",
        "geom_column": "geom",
    },
}


@tool
def spatial_accessibility_analyzer(
    area: str,
    radius_meters: int = 2000,
    facility_type: str = "all",
) -> dict:
    """Analyze spatial accessibility for a given area. Calculates how many
    facilities of a given type are reachable within a radius from the area centroid.
    Use this when the user asks 'how many X within Y km of Z',
    'walkable distance to X', 'nearby facilities', or 'accessibility'.

    Args:
        area: SA2 area name, e.g. 'Parramatta'.
        radius_meters: Search radius in meters. Default 2000 (2km).
        facility_type: Type of facility. One of 'clinic', 'school',
                       'transport', 'playground', 'community', or 'all'.
    """
    import os
    import pandas as pd
    from data_warehouse.connection import DatabaseManager

    config = {"database": {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "db_name": os.environ.get("DB_NAME", "geoanalysis"),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "schema": "public",
    }}

    _, conn = DatabaseManager(config).connect()

    try:
        # Get area centroid
        centroid_sql = f"""
        SELECT
            ST_X(ST_Centroid(geom)) AS lng,
            ST_Y(ST_Centroid(geom)) AS lat
        FROM sa2_regions
        WHERE "SA2_NAME21" = '{area}'
        LIMIT 1;
        """
        centroid_df = pd.read_sql_query(centroid_sql, conn)

        if centroid_df.empty:
            return {
                "error": "area_not_found",
                "message": f"未找到区域 '{area}'。请检查区域名称是否正确。",
            }

        center_lat = float(centroid_df["lat"].iloc[0])
        center_lng = float(centroid_df["lng"].iloc[0])

        # Determine which facility tables to query
        if facility_type == "all":
            types_to_query = list(FACILITY_TABLE_MAP.keys())
        else:
            if facility_type not in FACILITY_TABLE_MAP:
                return {
                    "error": "invalid_facility_type",
                    "message": f"未知设施类型 '{facility_type}'。"
                               f"可选: {list(FACILITY_TABLE_MAP.keys())}",
                }
            types_to_query = [facility_type]

        results = {}
        total_count = 0

        for ftype in types_to_query:
            info = FACILITY_TABLE_MAP[ftype]
            table = info["table"]

            # For tables with point geometry, use ST_DWithin
            if "geom_column" in info:
                geom_col = info["geom_column"]
                # Approximate degree-to-meter: 111,320 meters per degree
                radius_deg = radius_meters / 111320.0

                sql = f"""
                SELECT COUNT(*) AS cnt
                FROM {table}
                WHERE ST_DWithin(
                    geom,
                    ST_SetSRID(ST_MakePoint({center_lng}, {center_lat}), 4283),
                    {radius_deg}
                );
                """
                df = pd.read_sql_query(sql, conn)
                count = int(df["cnt"].iloc[0])
            else:
                # For POI counts (pre-aggregated by SA2), count in all areas
                # whose centroid is within the radius
                radius_deg = radius_meters / 111320.0
                sql = f"""
                SELECT SUM(pc.poi_count) AS cnt
                FROM poi_counts pc
                JOIN sa2_regions sr ON pc.sa2_code = sr."SA2_CODE21"
                WHERE ST_DWithin(
                    ST_Centroid(sr.geom),
                    ST_SetSRID(ST_MakePoint({center_lng}, {center_lat}), 4283),
                    {radius_deg}
                );
                """
                df = pd.read_sql_query(sql, conn)
                count = int(df["cnt"].iloc[0]) if pd.notna(df["cnt"].iloc[0]) else 0

            results[ftype] = {
                "count": count,
                "description": info["description"],
            }
            total_count += count

        return {
            "area": area,
            "center": {"lat": round(center_lat, 4), "lng": round(center_lng, 4)},
            "radius_m": radius_meters,
            "facility_type": facility_type,
            "total_facilities": total_count,
            "breakdown": results,
            "coverage_estimate": (
                f"以{area}质心为圆心、{radius_meters}米半径范围内，"
                f"共有 {total_count} 个设施。"
            ),
        }
    finally:
        conn.close()
