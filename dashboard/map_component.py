"""Lightweight interactive Sydney SA2 map.

Strategy:
- Pre-simplify geometries (0.002 tolerance → 96% smaller)
- Only 109 focus areas + neighbors (not all 373 SA2s)
- Inline Leaflet HTML with pre-computed GeoJSON (~300KB vs 19MB)
- No Folium dependency in hot path
"""
import json, os, psycopg2, pandas as pd, geopandas as gpd
from pathlib import Path
from typing import Optional, List
from shapely.geometry import mapping

FOCUS_SA4 = [
    'Sydney - Inner South West',
    'Sydney - Parramatta',
    'Sydney - South West',
]
SIMPLIFY_TOLERANCE = 0.002  # ~200m at Sydney latitude
COORD_DECIMALS = 5

_CACHED_JSON: Optional[str] = None  # In-memory cache


def _get_pw():
    try:
        with open("Credentials.json") as f:
            return json.load(f)["password"]
    except Exception:
        return os.environ.get("DB_PASSWORD", "")


def _build_geojson() -> dict:
    """Build simplified GeoJSON for focus SA2 areas + immediate neighbors."""
    sa2_dir = Path("SA2_2021_AUST_SHP_GDA2020")
    gdf = gpd.read_file(sa2_dir).to_crs(epsg=4326)

    # Simplify
    gdf['geometry'] = gdf['geometry'].simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)

    # Get focus areas
    focus_mask = gdf['SA4_NAME21'].isin(FOCUS_SA4)
    focus_codes = set(gdf.loc[focus_mask, 'SA2_CODE21'])

    # Also include direct neighbors of focus areas (for context)
    neighbor_codes = set()
    for _, row in gdf[focus_mask].iterrows():
        touches = gdf[gdf.geometry.touches(row.geometry)]
        neighbor_codes.update(touches['SA2_CODE21'].tolist())

    include_codes = focus_codes | neighbor_codes
    gdf = gdf[gdf['SA2_CODE21'].isin(include_codes)]

    # Load scores
    pw = _get_pw()
    raw = psycopg2.connect(host='localhost', port=5432, dbname='geoanalysis', user='postgres', password=pw)
    scores = pd.read_sql_query("SELECT sa2_name, final_score, rank_overall FROM well_resourced_scores", raw)
    raw.close()

    gdf = gdf.merge(scores, left_on='SA2_NAME21', right_on='sa2_name', how='left')

    # Round coordinates
    def round_coords(geom):
        g = mapping(geom)
        def _round_ring(coords):
            return [[round(x, COORD_DECIMALS), round(y, COORD_DECIMALS)] for x, y in coords]
        if g['type'] == 'Polygon':
            g['coordinates'] = [_round_ring(r) for r in g['coordinates']]
        elif g['type'] == 'MultiPolygon':
            g['coordinates'] = [[_round_ring(r) for r in p] for p in g['coordinates']]
        return g

    features = []
    for _, row in gdf.iterrows():
        geom = round_coords(row.geometry)
        props = {
            'name': row['SA2_NAME21'],
            'sa4': row.get('SA4_NAME21', ''),
            'score': round(float(row['final_score']), 3) if pd.notna(row.get('final_score')) else None,
            'rank': int(row['rank_overall']) if pd.notna(row.get('rank_overall')) else None,
            'is_focus': row['SA2_CODE21'] in focus_codes,
        }
        features.append({'type': 'Feature', 'properties': props, 'geometry': geom})

    return {'type': 'FeatureCollection', 'features': features}


def _color_for_score(score):
    """Viridis-inspired gradient: red(low) → yellow(mid) → green(high)."""
    if score is None:
        return '#2d2d3a'
    # Clamp
    s = max(0.0, min(1.0, score))
    if s < 0.25:
        return '#d73027'
    elif s < 0.5:
        return '#fc8d59'
    elif s < 0.75:
        return '#fee08b'
    else:
        return '#1a9850'


def quick_map_html(highlight_areas: Optional[List[str]] = None) -> str:
    """Return lightweight interactive map as self-contained HTML iframe (~300KB)."""
    global _CACHED_JSON

    # Build or reuse cached GeoJSON
    if _CACHED_JSON is None:
        geojson = _build_geojson()
        _CACHED_JSON = json.dumps(geojson, ensure_ascii=False)
        print(f"Map GeoJSON cached: {len(_CACHED_JSON):,} bytes ({len(geojson['features'])} features)")

    geojson_str = _CACHED_JSON
    highlight_set = set(a.lower() for a in (highlight_areas or []))

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9/dist/leaflet.min.css"/>
<style>
*{{margin:0;padding:0}} html,body{{width:100%;height:100%;overflow:hidden;background:#0d0d1a}}
#map{{width:100%;height:100%}}
.leaflet-container{{background:#0d0d1a!important;font-family:'Segoe UI',sans-serif}}
.info-panel{{position:absolute;bottom:16px;left:12px;z-index:999;background:rgba(10,10,24,0.92);border:1px solid rgba(100,100,160,0.3);border-radius:8px;padding:10px 14px;color:#c0c0d0;font-size:11px;pointer-events:none}}
.info-panel strong{{color:#f59e0b}}
</style></head><body>
<div id="map"></div>
<div class="info-panel">
  <strong>🏙️ Sydney SA2</strong><br>
  <span style="color:#1a9850">■</span> High RAI &nbsp;
  <span style="color:#d73027">■</span> Low RAI &nbsp;
  <span style="color:#2d2d3a">■</span> Non-focus
</div>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9/dist/leaflet.min.js"></script>
<script>
var data = {geojson_str};
var highlights = {json.dumps(list(highlight_set))};
var map = L.map('map', {{zoomControl:true, attributionControl:false}}).setView([-33.87,151.0],11);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{maxZoom:18}}).addTo(map);

function style(f){{
  var p=f.properties, score=p.score, name=(p.name||'').toLowerCase();
  var isHL = highlights.some(function(h){{return name.indexOf(h)>=0}});
  if(p.is_focus){{
    return {{fillColor: '{_color_for_score}' + (score!=null ? ('#' + ['d73027','fc8d59','fee08b','91cf60','1a9850'][Math.min(4,Math.floor((score-0.02)/0.2))] || '1a9850') : '#2d2d3a'),
      color: isHL?'#ff6b35':'#444',weight:isHL?3:0.5,fillOpacity:0.82}};
  }}
  return {{fillColor:'#1a1a2e',color:'#2a2a3a',weight:0.3,fillOpacity:0.15,dashArray:'4 4'}};
}}

// Use inline color function since JS can't use Python one
function colorForScore(s){{
  if(s==null)return'#2d2d3a';
  var stops=['#d73027','#fc8d59','#fee08b','#91cf60','#1a9850'];
  return stops[Math.min(4,Math.floor(s*5))]||stops[4];
}}

function style2(f){{
  var p=f.properties, name=(p.name||'').toLowerCase();
  var isHL=highlights.some(function(h){{return name.indexOf(h)>=0}});
  if(p.is_focus){{
    return {{fillColor:colorForScore(p.score),color:isHL?'#ff6b35':'#555',weight:isHL?3:0.5,fillOpacity:0.82}};
  }}
  return {{fillColor:'#1a1a2e',color:'#2a2a3a',weight:0.3,fillOpacity:0.15,dashArray:'4 4'}};
}}

L.geoJSON(data,{{
  style:style2,
  onEachFeature:function(f,layer){{
    var p=f.properties;
    layer.bindTooltip('<b>'+p.name+'</b><br>RAI: '+(p.score!=null?p.score.toFixed(3):'N/A')+'<br>SA4: '+p.sa4);
  }}
}}).addTo(map);
</script></body></html>"""

    import base64
    encoded = base64.b64encode(html.encode()).decode()
    return f'<iframe src="data:text/html;base64,{encoded}" width="100%" height="580px" style="border:none;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,0.4)" title="Sydney SA2 Map"></iframe>'
