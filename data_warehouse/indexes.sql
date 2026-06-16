-- ============================================================
-- GeoAnalysis Agent — Spatial Indexes (PostGIS GiST)
-- ============================================================

-- SA2 regions (core spatial join table)
CREATE INDEX IF NOT EXISTS idx_sa2_regions_geom
    ON public.sa2_regions USING GIST (geom);

-- Transport stops (114,718 points → GiST critical)
CREATE INDEX IF NOT EXISTS idx_stopcount_geom
    ON public.stopcount USING GIST (geom);

-- School catchments (2,128 polygons → GiST critical)
CREATE INDEX IF NOT EXISTS idx_schoolcatch_geom
    ON public.schoolcatch USING GIST (geom);

-- Polling places
CREATE INDEX IF NOT EXISTS idx_pollingplaces_geom
    ON public.pollingplaces USING GIST (geom);

-- Playgrounds
CREATE INDEX IF NOT EXISTS idx_playgrounds_geom
    ON public.playgrounds USING GIST (geom);

-- Business lookup indexes
CREATE INDEX IF NOT EXISTS idx_businesses_sa2_code
    ON public.businesses (sa2_code);
CREATE INDEX IF NOT EXISTS idx_businesses_industry_code
    ON public.businesses (industry_code);

-- Population lookup
CREATE INDEX IF NOT EXISTS idx_popall_sa2_code
    ON public.popall (sa2_code);

-- Income lookup
CREATE INDEX IF NOT EXISTS idx_income_sa2_code
    ON public.incomevalue (sa2_code21);

-- POI lookup
CREATE INDEX IF NOT EXISTS idx_poi_counts_sa2_code
    ON public.poi_counts (sa2_code);

-- Scores lookup
CREATE INDEX IF NOT EXISTS idx_scores_sa2_code
    ON public.well_resourced_scores (sa2_code);
