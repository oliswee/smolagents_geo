-- ============================================================
-- GeoAnalysis Agent — Views for Resource Scoring
-- ============================================================
-- All Z-Score + Sigmoid RAI computation in pure SQL.
-- Agent layer only SELECTs from these views — never generates SQL.
-- ============================================================

-- -----------------------------------------------------------
-- Sigmoid helper function
-- -----------------------------------------------------------
CREATE OR REPLACE FUNCTION public.sigmoid(x DOUBLE PRECISION)
RETURNS DOUBLE PRECISION AS $$
BEGIN
    RETURN 1.0 / (1.0 + EXP(-x));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- -----------------------------------------------------------
-- 1. Population Summary (total + youth_population)
-- -----------------------------------------------------------
DROP VIEW IF EXISTS public.pop_summary_view CASCADE;
CREATE VIEW public.pop_summary_view AS
SELECT
    popall.*,
    sa2_regions.geom,
    (
        popall."0-4_people"   + popall."5-9_people"    +
        popall."10-14_people"  + popall."15-19_people"  +
        popall."20-24_people"  + popall."25-29_people"  +
        popall."30-34_people"  + popall."35-39_people"  +
        popall."40-44_people"  + popall."45-49_people"  +
        popall."50-54_people"  + popall."55-59_people"  +
        popall."60-64_people"  + popall."65-69_people"  +
        popall."70-74_people"  + popall."75-79_people"  +
        popall."80-84_people"  + popall."85-and-over_people"
    ) AS total_population
FROM popall
INNER JOIN sa2_regions ON popall.sa2_code = sa2_regions."SA2_CODE21";

-- -----------------------------------------------------------
-- 2. Total Population (filtered: >= 100)
-- -----------------------------------------------------------
DROP VIEW IF EXISTS public.total_pop_view CASCADE;
CREATE VIEW public.total_pop_view AS
SELECT
    sa2_code,
    total_population,
    ("0-4_people" + "5-9_people" + "10-14_people" + "15-19_people") AS youth_population
FROM pop_summary_view
WHERE total_population >= 100;

-- -----------------------------------------------------------
-- 3. Business Score (manufacturing / 1000 people)
-- -----------------------------------------------------------
DROP VIEW IF EXISTS public.business_score_view CASCADE;
CREATE VIEW public.business_score_view AS
SELECT
    b.sa2_code,
    SUM(b.total_businesses) AS manufacturing_businesses,
    tp.total_population,
    CASE
        WHEN tp.total_population > 0
        THEN (SUM(b.total_businesses)::FLOAT / tp.total_population) * 1000
        ELSE 0
    END AS businesses_per_1000
FROM businesses b
JOIN total_pop_view tp ON b.sa2_code = tp.sa2_code
WHERE b.industry_name = 'Manufacturing'
  AND tp.total_population >= 100
GROUP BY b.sa2_code, tp.total_population;

-- -----------------------------------------------------------
-- 4. Transport Stops Score (stops per capita)
-- -----------------------------------------------------------
DROP VIEW IF EXISTS public.stops_score_view CASCADE;
CREATE VIEW public.stops_score_view AS
SELECT
    sr."SA2_CODE21" AS sa2_code,
    COUNT(s.stop_id) AS stop_count,
    tp.total_population,
    CASE
        WHEN tp.total_population > 0
        THEN COUNT(s.stop_id)::FLOAT / tp.total_population
        ELSE 0
    END AS stops_per_capita
FROM sa2_regions sr
LEFT JOIN stopcount s ON ST_Contains(sr.geom, s.geom)
JOIN total_pop_view tp ON sr."SA2_CODE21" = tp.sa2_code
WHERE tp.total_population >= 100
GROUP BY sr."SA2_CODE21", tp.total_population;

-- -----------------------------------------------------------
-- 5. Schools Score (schools / 1000 youth)
-- -----------------------------------------------------------
DROP VIEW IF EXISTS public.schools_score_view CASCADE;
CREATE VIEW public.schools_score_view AS
SELECT
    sr."SA2_CODE21" AS sa2_code,
    COUNT(DISTINCT sc."USE_DESC") AS school_count,
    SUM(sc.area_km2) AS total_catchment_area,
    tp.youth_population,
    CASE
        WHEN tp.youth_population > 0
        THEN (COUNT(DISTINCT sc."USE_DESC")::FLOAT / tp.youth_population) * 1000
        ELSE 0
    END AS schools_per_1000_youth
FROM sa2_regions sr
LEFT JOIN schoolcatch sc ON ST_Intersects(sr.geom, sc.geom)
JOIN total_pop_view tp ON sr."SA2_CODE21" = tp.sa2_code
WHERE tp.total_population >= 100
GROUP BY sr."SA2_CODE21", tp.youth_population;

-- -----------------------------------------------------------
-- 6. POI Score (POI per capita)
-- -----------------------------------------------------------
DROP VIEW IF EXISTS public.poi_score_view CASCADE;
CREATE VIEW public.poi_score_view AS
SELECT
    pc.sa2_code,
    pc.poi_count,
    tp.total_population,
    CASE
        WHEN tp.total_population > 0
        THEN pc.poi_count::FLOAT / tp.total_population
        ELSE 0
    END AS poi_per_capita
FROM poi_counts pc
JOIN total_pop_view tp ON pc.sa2_code = tp.sa2_code
WHERE tp.total_population >= 100;

-- -----------------------------------------------------------
-- 7. Combined Metrics (all four dimensions)
-- -----------------------------------------------------------
DROP VIEW IF EXISTS public.combined_metrics_view CASCADE;
CREATE VIEW public.combined_metrics_view AS
SELECT
    sr."SA2_CODE21" AS sa2_code,
    sr."SA2_NAME21" AS sa2_name,
    sr."SA4_NAME21" AS sa4_name,
    COALESCE(bs.businesses_per_1000, 0)   AS businesses_per_1000,
    COALESCE(ss.stops_per_capita, 0)      AS stops_per_capita,
    COALESCE(scs.schools_per_1000_youth, 0) AS schools_per_1000_youth,
    COALESCE(ps.poi_per_capita, 0)        AS poi_per_capita,
    tp.total_population
FROM selected_sa2_regions sr
JOIN total_pop_view tp ON sr."SA2_CODE21" = tp.sa2_code
LEFT JOIN business_score_view bs  ON sr."SA2_CODE21" = bs.sa2_code
LEFT JOIN stops_score_view ss     ON sr."SA2_CODE21" = ss.sa2_code
LEFT JOIN schools_score_view scs  ON sr."SA2_CODE21" = scs.sa2_code
LEFT JOIN poi_score_view ps       ON sr."SA2_CODE21" = ps.sa2_code
WHERE tp.total_population >= 100;

-- -----------------------------------------------------------
-- 8. Well-Resourced Scores (Z-Score + Sigmoid → 0-1 RAI)
--    This is the core view that Agent queries.
-- -----------------------------------------------------------
DROP VIEW IF EXISTS public.well_resourced_scores_view CASCADE;
CREATE VIEW public.well_resourced_scores_view AS
WITH stats AS (
    SELECT
        AVG(businesses_per_1000)   AS mean_business,
        STDDEV(businesses_per_1000) AS stddev_business,
        AVG(stops_per_capita)      AS mean_stops,
        STDDEV(stops_per_capita)   AS stddev_stops,
        AVG(schools_per_1000_youth) AS mean_schools,
        STDDEV(schools_per_1000_youth) AS stddev_schools,
        AVG(poi_per_capita)        AS mean_poi,
        STDDEV(poi_per_capita)     AS stddev_poi,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY businesses_per_1000)   AS median_business,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY stops_per_capita)      AS median_stops,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY schools_per_1000_youth) AS median_schools,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY poi_per_capita)        AS median_poi
    FROM combined_metrics_view
)
SELECT
    cm.sa2_code,
    cm.sa2_name,
    cm.sa4_name,
    cm.businesses_per_1000,
    cm.stops_per_capita,
    cm.schools_per_1000_youth,
    cm.poi_per_capita,
    cm.total_population,
    s.median_business,
    s.median_stops,
    s.median_schools,
    s.median_poi,
    -- Z-Scores (with zero-division guard)
    CASE WHEN s.stddev_business = 0 OR s.stddev_business IS NULL THEN 0
         ELSE (cm.businesses_per_1000 - s.mean_business) / s.stddev_business
    END AS z_business,
    CASE WHEN s.stddev_stops = 0 OR s.stddev_stops IS NULL THEN 0
         ELSE (cm.stops_per_capita - s.mean_stops) / s.stddev_stops
    END AS z_stops,
    CASE WHEN s.stddev_schools = 0 OR s.stddev_schools IS NULL THEN 0
         ELSE (cm.schools_per_1000_youth - s.mean_schools) / s.stddev_schools
    END AS z_schools,
    CASE WHEN s.stddev_poi = 0 OR s.stddev_poi IS NULL THEN 0
         ELSE (cm.poi_per_capita - s.mean_poi) / s.stddev_poi
    END AS z_poi,
    -- Composite Z-Score
    (
        CASE WHEN s.stddev_business = 0 OR s.stddev_business IS NULL THEN 0
             ELSE (cm.businesses_per_1000 - s.mean_business) / s.stddev_business
        END +
        CASE WHEN s.stddev_stops = 0 OR s.stddev_stops IS NULL THEN 0
             ELSE (cm.stops_per_capita - s.mean_stops) / s.stddev_stops
        END +
        CASE WHEN s.stddev_schools = 0 OR s.stddev_schools IS NULL THEN 0
             ELSE (cm.schools_per_1000_youth - s.mean_schools) / s.stddev_schools
        END +
        CASE WHEN s.stddev_poi = 0 OR s.stddev_poi IS NULL THEN 0
             ELSE (cm.poi_per_capita - s.mean_poi) / s.stddev_poi
        END
    ) AS z_total,
    -- Final RAI Score (0-1 via Sigmoid)
    public.sigmoid(
        CASE WHEN s.stddev_business = 0 OR s.stddev_business IS NULL THEN 0
             ELSE (cm.businesses_per_1000 - s.mean_business) / s.stddev_business
        END +
        CASE WHEN s.stddev_stops = 0 OR s.stddev_stops IS NULL THEN 0
             ELSE (cm.stops_per_capita - s.mean_stops) / s.stddev_stops
        END +
        CASE WHEN s.stddev_schools = 0 OR s.stddev_schools IS NULL THEN 0
             ELSE (cm.schools_per_1000_youth - s.mean_schools) / s.stddev_schools
        END +
        CASE WHEN s.stddev_poi = 0 OR s.stddev_poi IS NULL THEN 0
             ELSE (cm.poi_per_capita - s.mean_poi) / s.stddev_poi
        END
    ) AS final_score,
    i.median_income
FROM combined_metrics_view cm
CROSS JOIN stats s
LEFT JOIN incomevalue i ON cm.sa2_code = i.sa2_code21;

-- -----------------------------------------------------------
-- 9. Materialized table (optional — faster queries)
-- -----------------------------------------------------------
DROP TABLE IF EXISTS public.well_resourced_scores CASCADE;
CREATE TABLE public.well_resourced_scores AS
SELECT * FROM public.well_resourced_scores_view;

-- Add rank columns
ALTER TABLE public.well_resourced_scores
    ADD COLUMN rank_overall INTEGER,
    ADD COLUMN rank_business INTEGER,
    ADD COLUMN rank_stops INTEGER,
    ADD COLUMN rank_schools INTEGER,
    ADD COLUMN rank_poi INTEGER;

-- Populate ranks
UPDATE public.well_resourced_scores SET rank_overall  = r.rnk FROM (SELECT sa2_code, RANK() OVER (ORDER BY final_score DESC) AS rnk FROM public.well_resourced_scores) r WHERE well_resourced_scores.sa2_code = r.sa2_code;
UPDATE public.well_resourced_scores SET rank_business = r.rnk FROM (SELECT sa2_code, RANK() OVER (ORDER BY z_business DESC) AS rnk FROM public.well_resourced_scores) r WHERE well_resourced_scores.sa2_code = r.sa2_code;
UPDATE public.well_resourced_scores SET rank_stops    = r.rnk FROM (SELECT sa2_code, RANK() OVER (ORDER BY z_stops DESC)    AS rnk FROM public.well_resourced_scores) r WHERE well_resourced_scores.sa2_code = r.sa2_code;
UPDATE public.well_resourced_scores SET rank_schools  = r.rnk FROM (SELECT sa2_code, RANK() OVER (ORDER BY z_schools DESC)  AS rnk FROM public.well_resourced_scores) r WHERE well_resourced_scores.sa2_code = r.sa2_code;
UPDATE public.well_resourced_scores SET rank_poi      = r.rnk FROM (SELECT sa2_code, RANK() OVER (ORDER BY z_poi DESC)      AS rnk FROM public.well_resourced_scores) r WHERE well_resourced_scores.sa2_code = r.sa2_code;
