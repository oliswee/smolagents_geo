"""Skill 1: Resource Gap Detector.

Identifies areas with resource deficiencies based on the RAI
four-dimension scoring system. All calculations are in pre-built
PostgreSQL views — this tool only SELECTs, never computes.
"""
from smolagents import tool
import pandas as pd


# Cache the full 109-area list for parameter validation
_VALID_AREAS: list[str] | None = None


def _load_valid_areas(conn) -> list[str]:
    """Load the list of all 109 SA2 area names from the database."""
    global _VALID_AREAS
    if _VALID_AREAS is None:
        df = pd.read_sql_query(
            'SELECT "SA2_NAME21" FROM selected_sa2_regions ORDER BY "SA2_NAME21"',
            conn,
        )
        _VALID_AREAS = [name.lower() for name in df["SA2_NAME21"].tolist()]
    return _VALID_AREAS


def _validate_areas(areas: list[str], conn) -> dict | None:
    """Validate area names. Returns error dict if any are invalid."""
    valid = _load_valid_areas(conn)
    invalid = [a for a in areas if a.lower() not in valid]
    if invalid:
        # Find closest matches
        candidates = []
        for name in invalid:
            matches = [v for v in valid if name.lower()[:3] in v]
            candidates.extend(matches[:3])
        return {
            "error": "invalid_area",
            "invalid_names": invalid,
            "candidates": list(set(candidates)),
            "hint": "请从以上候选区域中选择，或输入完整的 SA2 区域名称。",
        }
    return None


def _normalize_area_name(name: str, conn) -> str:
    """Match user input (possibly lowercase) to exact DB name."""
    valid = _load_valid_areas(conn)
    for v in valid:
        if name.lower() == v.lower():
            return v
    return name  # Return as-is; caller should validate first


@tool
def resource_gap_detector(
    areas: list[str] | None = None,
    dimension: str = "all",
    top_n: int = 5,
) -> dict:
    """Identify resource gap areas based on the RAI four-dimension scoring system.
    Use this when the user asks about 'which areas lack resources',
    'resource shortages', 'gap analysis', or 'XX area's weaknesses'.
    Use this to compare areas or rank them by resource availability.

    Args:
        areas: List of SA2 area names, e.g. ['Parramatta', 'Auburn'].
               None or empty list means analyze all 109 areas.
        dimension: The resource dimension to check.
                   One of '商业活力', '交通可达性', '教育覆盖', '公共服务', or 'all'.
        top_n: Number of top gap areas to return. Default 5.
    """
    import os
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
        # Parameter validation
        if areas:
            error = _validate_areas(areas, conn)
            if error:
                return error
            normalized = [_normalize_area_name(a, conn) for a in areas]
            area_filter = f"""AND w."sa2_name" IN ({','.join(f"'{n}'" for n in normalized)})"""
        else:
            area_filter = ""

        # Dimension mapping
        dim_col = {
            "商业活力": "z_business",
            "交通可达性": "z_stops",
            "教育覆盖": "z_schools",
            "公共服务": "z_poi",
        }

        if dimension == "all":
            order_col = "final_score"
            ascending = True  # Lower score = bigger gap
        else:
            order_col = f'"{dim_col[dimension]}"'
            ascending = True

        sql = f"""
        SELECT
            sa2_name,
            sa4_name,
            final_score,
            rank_overall,
            z_business,
            z_stops,
            z_schools,
            z_poi,
            median_income
        FROM well_resourced_scores w
        WHERE 1=1 {area_filter}
        ORDER BY {order_col} {'ASC' if ascending else 'DESC'}
        LIMIT {top_n};
        """

        df = pd.read_sql_query(sql, conn)

        gaps = []
        for _, row in df.iterrows():
            z_scores = {
                "商业活力": round(float(row["z_business"]), 3),
                "交通可达性": round(float(row["z_stops"]), 3),
                "教育覆盖": round(float(row["z_schools"]), 3),
                "公共服务": round(float(row["z_poi"]), 3),
            }

            # Identify weakest dimension
            weakest = min(z_scores, key=z_scores.get)

            gaps.append({
                "suburb": row["sa2_name"],
                "sa4_name": row["sa4_name"],
                "final_score": round(float(row["final_score"]), 4),
                "rank": int(row["rank_overall"]),
                "z_scores": z_scores,
                "weakest_dimension": weakest,
                "median_income": round(float(row["median_income"]), 0)
                    if pd.notna(row.get("median_income")) else None,
            })

        return {
            "gaps": gaps,
            "query_params": {
                "areas": areas or "all 109 areas",
                "dimension": dimension,
                "top_n": top_n,
            },
            "total_areas_analyzed": 109 if not areas else len(areas),
        }
    finally:
        conn.close()
