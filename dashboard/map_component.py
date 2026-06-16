"""Interactive Folium map builder for Sydney SA2 regions.

Builds an interactive Leaflet map with:
- 109 focus SA2 regions color-coded by RAI score (viridis)
- Click-to-query: clicking a region auto-fills the chat box
- Hover tooltips with area name + score
- Highlight overlay for search results
"""
import folium
from folium import FeatureGroup, GeoJson, LayerControl
import pandas as pd
import geopandas as gpd
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
import branca.colormap as cm


def build_sydney_map(
    scores_df: Optional[pd.DataFrame] = None,
    highlight_areas: Optional[List[str]] = None,
    highlight_color: str = "#ff6b35",
) -> folium.Map:
    """Build the main interactive Sydney map.

    Args:
        scores_df: DataFrame with SA2_NAME21, final_score columns.
        highlight_areas: List of area names to highlight with a border.
        highlight_color: Hex color for highlight border.

    Returns:
        folium.Map object (can be rendered to HTML or saved).
    """
    # ── Load SA2 geometry ──────────────────────────────────
    sa2_dir = Path("SA2_2021_AUST_SHP_GDA2020")
    gdf = gpd.read_file(sa2_dir)
    gdf = gdf[gdf['GCC_NAME21'] == 'Greater Sydney'].to_crs(epsg=4326)

    focus_sa4 = [
        'Sydney - Inner South West',
        'Sydney - Parramatta',
        'Sydney - South West',
    ]
    gdf['is_focus'] = gdf['SA4_NAME21'].isin(focus_sa4)

    # ── Merge scores if provided ───────────────────────────
    if scores_df is not None and len(scores_df) > 0:
        gdf = gdf.merge(
            scores_df[['sa2_name', 'final_score', 'rank_overall']],
            left_on='SA2_NAME21', right_on='sa2_name', how='left'
        )
        has_scores = True
    else:
        gdf['final_score'] = None
        has_scores = False

    # ── Center on Sydney ───────────────────────────────────
    m = folium.Map(
        location=[-33.87, 151.00],
        zoom_start=11,
        tiles='CartoDB dark_matter',
        zoom_control=True,
        prefer_canvas=True,
    )

    # ── Color scale ────────────────────────────────────────
    if has_scores:
        score_min = gdf['final_score'].min()
        score_max = gdf['final_score'].max()
        colormap = cm.LinearColormap(
            colors=['#d73027', '#fc8d59', '#fee08b', '#91cf60', '#1a9850'],
            vmin=score_min, vmax=score_max,
            caption='资源充裕度指数 (RAI)'
        )

        def style_function(feature):
            score = feature['properties'].get('final_score')
            if score is None or pd.isna(score):
                return {
                    'fillColor': '#2d2d2d',
                    'color': '#444444',
                    'weight': 0.5,
                    'fillOpacity': 0.15,
                }
            color = colormap(score)
            area_name = feature['properties'].get('SA2_NAME21', '')
            is_highlighted = highlight_areas and any(
                a.lower() in area_name.lower() for a in highlight_areas
            )
            return {
                'fillColor': color,
                'color': highlight_color if is_highlighted else '#666666',
                'weight': 3 if is_highlighted else 0.5,
                'fillOpacity': 0.85 if feature['properties'].get('is_focus') else 0.15,
                'dashArray': None if feature['properties'].get('is_focus') else '5,5',
            }
    else:
        colormap = None

        def style_function(feature):
            return {
                'fillColor': '#fee08b' if feature['properties'].get('is_focus')
                             else '#2d2d2d',
                'color': '#666666',
                'weight': 1 if feature['properties'].get('is_focus') else 0.3,
                'fillOpacity': 0.6 if feature['properties'].get('is_focus') else 0.1,
            }

    # ── GeoJSON layer ─═════════════════════════════════════
    geo_json = GeoJson(
        data=gdf.__geo_interface__,
        style_function=style_function,
        highlight_function=lambda x: {
            'fillColor': '#ffffff',
            'color': '#ffffff',
            'weight': 3,
            'fillOpacity': 0.3,
            'transition': 'fill-opacity 0.2s ease-out',
        },
        tooltip=folium.GeoJsonTooltip(
            fields=['SA2_NAME21', 'final_score', 'SA4_NAME21'],
            aliases=['区域:', 'RAI 评分:', 'SA4 区域:'],
            localize=True,
            sticky=False,
            labels=True,
            style="""
                background-color: #1a1a2e;
                border: 1px solid #333355;
                border-radius: 6px;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
                padding: 8px 12px;
            """,
            max_width=280,
        ),
        name='SA2 Regions',
    )
    geo_json.add_to(m)

    # ── Color legend ───────────────────────────────────────
    if colormap:
        colormap.add_to(m)

    # ── Legend overlay ─────────────────────────────────────
    legend_html = f"""
    <div style="
        position: fixed; bottom: 30px; left: 15px; z-index: 9999;
        background: rgba(26,26,46,0.92);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(51,51,85,0.6);
        border-radius: 10px;
        padding: 14px 18px;
        color: #c0c0d0;
        font-family: 'Segoe UI', system-ui, sans-serif;
        font-size: 11px;
        line-height: 1.7;
        pointer-events: none;
        max-width: 240px;
    ">
        <div style="font-size:13px;font-weight:700;color:#e8e8f0;margin-bottom:6px;">
            🏙️ Sydney SA2 Regions
        </div>
        <div style="display:flex;align-items:center;gap:6px;margin:3px 0;">
            <span style="width:12px;height:12px;border-radius:3px;background:#1a9850;"></span>
            <span>高资源充裕度</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px;margin:3px 0;">
            <span style="width:12px;height:12px;border-radius:3px;background:#d73027;"></span>
            <span>低资源充裕度</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px;margin:3px 0;">
            <span style="width:12px;height:12px;border-radius:3px;background:#2d2d2d;"></span>
            <span>非分析区域</span>
        </div>
        <div style="margin-top:8px;font-size:10px;color:#8888a0;">
            🟠 橙色边框 = 分析结果高亮
        </div>
    </div>
    """

    m.get_root().html.add_child(folium.Element(legend_html))

    # ── LayerControl ───────────────────────────────────────
    LayerControl(position='topright').add_to(m)

    return m


def map_to_html(m: folium.Map, width: str = "100%", height: str = "580px") -> str:
    """Convert a folium Map to an embeddable HTML iframe string.

    Returns an <iframe> tag suitable for gr.HTML().
    """
    html_content = m.get_root().render()

    # Wrap in a self-contained HTML document
    full_html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{ margin:0; padding:0; overflow:hidden; }}
  .folium-map {{ width:100%; height:100vh; }}
  .leaflet-container {{ background: #0d0d1a !important; }}
</style>
</head><body>
{html_content}
</body></html>"""

    # Encode as data URI to avoid file serving issues
    import base64
    encoded = base64.b64encode(full_html.encode()).decode()

    return f"""<iframe
    src="data:text/html;base64,{encoded}"
    width="{width}" height="{height}"
    style="border:none; border-radius:12px; box-shadow: 0 4px 24px rgba(0,0,0,0.4);"
    title="Sydney SA2 Map"
></iframe>"""


def quick_map_html(highlight_areas: Optional[List[str]] = None) -> str:
    """Convenience: build map with DB scores and return HTML iframe."""
    import psycopg2, os, json

    # Try env var first, then Credentials.json
    pw = os.environ.get("DB_PASSWORD", "")
    if not pw:
        try:
            with open("Credentials.json") as f:
                creds = json.load(f)
            pw = creds.get("password", "")
        except Exception:
            pass

    raw = psycopg2.connect(
        host='localhost', port=5432, dbname='geoanalysis',
        user='postgres', password=pw
    )
    df = pd.read_sql_query(
        "SELECT sa2_name, final_score, rank_overall FROM well_resourced_scores", raw
    )
    raw.close()
    m = build_sydney_map(df, highlight_areas=highlight_areas)
    return map_to_html(m)
