"""PostGIS MCP Server — exposes spatial query primitives as MCP tools.

Smolagents connects to this via ToolCollection.from_mcp() — one line
to import all spatial tools into the agent's tool registry.

Tools exposed:
  - query_buffer_poi: Count facilities within a radius
  - nearest_n_poi: Find N nearest facilities
  - service_area_coverage: Calculate walkable/drivable area coverage
"""
import os
import json
from mcp.server import Server
from mcp.types import Tool, TextContent


# Create MCP server
server = Server("postgis-mcp-server")


def _get_connection():
    """Get database connection from environment."""
    import psycopg2
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "geoanalysis"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
    )


@server.tool()
async def query_buffer_poi(
    center_lat: float,
    center_lng: float,
    radius_meters: int = 2000,
    poi_type: str = "all",
) -> str:
    """Count facilities within a radius of a center point.

    Args:
        center_lat: Center latitude (e.g. -33.8150)
        center_lng: Center longitude (e.g. 151.0011)
        radius_meters: Buffer radius in meters. Default 2000.
        poi_type: Facility type. One of 'transport', 'school', 'playground',
                  'polling', or 'all'.

    Returns:
        JSON string with facility counts by type.
    """
    radius_deg = radius_meters / 111320.0

    tables = {
        "transport": "stopcount",
        "school": "schoolcatch",
        "playground": "playgrounds",
        "polling": "pollingplaces",
    }

    if poi_type != "all" and poi_type not in tables:
        return json.dumps({
            "error": f"Unknown poi_type '{poi_type}'. Options: {list(tables.keys())}"
        })

    types_to_query = list(tables.keys()) if poi_type == "all" else [poi_type]

    conn = _get_connection()
    try:
        results = {}
        with conn.cursor() as cur:
            for ptype in types_to_query:
                table = tables[ptype]
                cur.execute(f"""
                    SELECT COUNT(*) FROM {table}
                    WHERE ST_DWithin(
                        geom,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4283),
                        %s
                    );
                """, (center_lng, center_lat, radius_deg))
                results[ptype] = cur.fetchone()[0]

        return json.dumps({
            "center": {"lat": center_lat, "lng": center_lng},
            "radius_m": radius_meters,
            "facility_counts": results,
            "total": sum(results.values()),
        })
    finally:
        conn.close()


@server.tool()
async def nearest_n_poi(
    center_lat: float,
    center_lng: float,
    n: int = 5,
    poi_type: str = "transport",
) -> str:
    """Find the N nearest facilities to a point.

    Args:
        center_lat: Center latitude.
        center_lng: Center longitude.
        n: Number of nearest facilities to return. Default 5.
        poi_type: Facility type. One of 'transport', 'playground', 'polling'.

    Returns:
        JSON string with nearest facilities and distances.
    """
    tables = {
        "transport": "stopcount",
        "playground": "playgrounds",
        "polling": "pollingplaces",
    }

    if poi_type not in tables:
        return json.dumps({
            "error": f"Unknown poi_type '{poi_type}'. Options: {list(tables.keys())}"
        })

    table = tables[poi_type]
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    ST_Distance(
                        geom,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4283)
                    ) * 111320.0 AS distance_m,
                    ST_AsText(geom) AS location
                FROM {table}
                ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4283)
                LIMIT %s;
            """, (center_lng, center_lat, center_lng, center_lat, n))

            facilities = [
                {"distance_m": round(row[0], 1), "location_wkt": row[1]}
                for row in cur.fetchall()
            ]

        return json.dumps({
            "center": {"lat": center_lat, "lng": center_lng},
            "facility_type": poi_type,
            "nearest": facilities,
        })
    finally:
        conn.close()


@server.tool()
async def service_area_coverage(
    sa2_code: str,
    travel_mode: str = "walking",
    time_minutes: int = 15,
) -> str:
    """Estimate service area coverage for an SA2 region.

    Uses a simplified buffer-based approach (not true network routing).
    For production, replace with pgRouting or external routing API.

    Args:
        sa2_code: SA2 region code (e.g. '119011358').
        travel_mode: 'walking' or 'driving'. Default 'walking'.
        time_minutes: Travel time threshold in minutes.

    Returns:
        JSON string with coverage statistics.
    """
    # Approximate speeds
    speed_mps = 1.4 if travel_mode == "walking" else 13.9  # m/s
    radius_m = speed_mps * time_minutes * 60

    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            # Get region centroid
            cur.execute("""
                SELECT ST_X(ST_Centroid(geom)), ST_Y(ST_Centroid(geom))
                FROM sa2_regions
                WHERE "SA2_CODE21" = %s;
            """, (sa2_code,))
            row = cur.fetchone()
            if not row:
                return json.dumps({"error": f"SA2 code '{sa2_code}' not found"})

            center_lng, center_lat = row

            # Count facilities within service radius
            radius_deg = radius_m / 111320.0
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM stopcount
                     WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4283), %s)) AS transport_stops,
                    (SELECT COUNT(*) FROM playgrounds
                     WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4283), %s)) AS playgrounds;
            """, (center_lng, center_lat, radius_deg, center_lng, center_lat, radius_deg))

            transport, playgrounds = cur.fetchone()

        # Coverage area (approximate circle)
        coverage_area_km2 = 3.14159 * (radius_m / 1000) ** 2

        return json.dumps({
            "sa2_code": sa2_code,
            "travel_mode": travel_mode,
            "time_minutes": time_minutes,
            "service_radius_m": round(radius_m, 0),
            "coverage_area_km2": round(coverage_area_km2, 2),
            "facilities_in_range": {
                "transport_stops": transport,
                "playgrounds": playgrounds,
            },
        })
    finally:
        conn.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(server.run())
