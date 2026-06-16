-- ============================================================
-- GeoAnalysis Agent — PostgreSQL + PostGIS Database Schema
-- ============================================================
-- SRID 4283 (GDA94) — Australian standard
-- ============================================================

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- 1. SA2 Regions (master spatial table)
-- ============================================================
DROP TABLE IF EXISTS public.sa2_regions CASCADE;
CREATE TABLE public.sa2_regions (
    "SA2_CODE21"  VARCHAR(9) PRIMARY KEY,
    "SA2_NAME21"  VARCHAR(100) NOT NULL,
    "SA4_CODE21"  VARCHAR(9),
    "SA4_NAME21"  VARCHAR(100),
    "STE_NAME21"  VARCHAR(50),
    geom          GEOMETRY(MULTIPOLYGON, 4283) NOT NULL
);

-- ============================================================
-- 2. Businesses (by industry × SA2)
-- ============================================================
DROP TABLE IF EXISTS public.businesses CASCADE;
CREATE TABLE public.businesses (
    id               SERIAL PRIMARY KEY,
    industry_code    VARCHAR(5) NOT NULL,
    industry_name    VARCHAR(100) NOT NULL,
    sa2_code         VARCHAR(9) NOT NULL,
    sa2_name         VARCHAR(100) NOT NULL,
    total_businesses INTEGER NOT NULL,
    CONSTRAINT fk_businesses_sa2 FOREIGN KEY (sa2_code)
        REFERENCES public.sa2_regions ("SA2_CODE21")
);

-- ============================================================
-- 3. Transport Stops (GTFS)
-- ============================================================
DROP TABLE IF EXISTS public.stopcount CASCADE;
CREATE TABLE public.stopcount (
    stop_id  VARCHAR(20) PRIMARY KEY,
    geom     GEOMETRY(POINT, 4283) NOT NULL
);

-- ============================================================
-- 4. School Catchments
-- ============================================================
DROP TABLE IF EXISTS public.schoolcatch CASCADE;
CREATE TABLE public.schoolcatch (
    id          SERIAL PRIMARY KEY,
    "USE_ID"    VARCHAR(20),
    "CATCH_TYPE" VARCHAR(20),
    "USE_DESC"  VARCHAR(200),
    geom        GEOMETRY(MULTIPOLYGON, 4283) NOT NULL,
    area_km2    DOUBLE PRECISION
);

-- ============================================================
-- 5. Population (19 age groups × SA2)
-- ============================================================
DROP TABLE IF EXISTS public.popall CASCADE;
CREATE TABLE public.popall (
    sa2_code              VARCHAR(9) PRIMARY KEY,
    sa2_name              VARCHAR(100),
    "0-4_people"          INTEGER DEFAULT 0,
    "5-9_people"          INTEGER DEFAULT 0,
    "10-14_people"        INTEGER DEFAULT 0,
    "15-19_people"        INTEGER DEFAULT 0,
    "20-24_people"        INTEGER DEFAULT 0,
    "25-29_people"        INTEGER DEFAULT 0,
    "30-34_people"        INTEGER DEFAULT 0,
    "35-39_people"        INTEGER DEFAULT 0,
    "40-44_people"        INTEGER DEFAULT 0,
    "45-49_people"        INTEGER DEFAULT 0,
    "50-54_people"        INTEGER DEFAULT 0,
    "55-59_people"        INTEGER DEFAULT 0,
    "60-64_people"        INTEGER DEFAULT 0,
    "65-69_people"        INTEGER DEFAULT 0,
    "70-74_people"        INTEGER DEFAULT 0,
    "75-79_people"        INTEGER DEFAULT 0,
    "80-84_people"        INTEGER DEFAULT 0,
    "85-and-over_people"  INTEGER DEFAULT 0,
    CONSTRAINT fk_popall_sa2 FOREIGN KEY (sa2_code)
        REFERENCES public.sa2_regions ("SA2_CODE21")
);

-- ============================================================
-- 6. Income
-- ============================================================
DROP TABLE IF EXISTS public.incomevalue CASCADE;
CREATE TABLE public.incomevalue (
    sa2_code21     VARCHAR(9) PRIMARY KEY,
    sa2_name       VARCHAR(100),
    earners        VARCHAR(20),
    median_age     VARCHAR(10),
    median_income  DOUBLE PRECISION,
    mean_income    VARCHAR(20),
    CONSTRAINT fk_income_sa2 FOREIGN KEY (sa2_code21)
        REFERENCES public.sa2_regions ("SA2_CODE21")
);

-- ============================================================
-- 7. POI Counts (from NSW API)
-- ============================================================
DROP TABLE IF EXISTS public.poi_counts CASCADE;
CREATE TABLE public.poi_counts (
    id         SERIAL PRIMARY KEY,
    sa2_code   VARCHAR(9) NOT NULL,
    sa2_name   VARCHAR(100) NOT NULL,
    sa4_name   VARCHAR(100) NOT NULL,
    poi_count  INTEGER NOT NULL,
    CONSTRAINT fk_poi_sa2 FOREIGN KEY (sa2_code)
        REFERENCES public.sa2_regions ("SA2_CODE21")
);

-- ============================================================
-- 8. Polling Places (AEC 2019)
-- ============================================================
DROP TABLE IF EXISTS public.pollingplaces CASCADE;
CREATE TABLE public.pollingplaces (
    id          SERIAL PRIMARY KEY,
    place_name  VARCHAR(200),
    address     VARCHAR(300),
    geom        GEOMETRY(POINT, 4283) NOT NULL
);

-- ============================================================
-- 9. Crimes (by suburb)
-- ============================================================
DROP TABLE IF EXISTS public.crimes CASCADE;
CREATE TABLE public.crimes (
    id           SERIAL PRIMARY KEY,
    suburb_name  VARCHAR(100),
    crime_type   VARCHAR(100),
    crime_rate   DOUBLE PRECISION,
    sa2_code     VARCHAR(9),
    CONSTRAINT fk_crimes_sa2 FOREIGN KEY (sa2_code)
        REFERENCES public.sa2_regions ("SA2_CODE21")
);

-- ============================================================
-- 10. Playgrounds & Fitness Stations (City of Sydney)
-- ============================================================
DROP TABLE IF EXISTS public.playgrounds CASCADE;
CREATE TABLE public.playgrounds (
    id              SERIAL PRIMARY KEY,
    facility_name   VARCHAR(200),
    facility_type   VARCHAR(50),  -- 'playground' | 'fitness'
    geom            GEOMETRY(POINT, 4283) NOT NULL
);

-- ============================================================
-- Selected SA4 Regions View (109 SA2 focus areas)
-- ============================================================
DROP VIEW IF EXISTS public.selected_sa2_regions CASCADE;
CREATE VIEW public.selected_sa2_regions AS
SELECT *
FROM public.sa2_regions
WHERE "SA4_NAME21" IN (
    'Sydney - Inner South West',
    'Sydney - Parramatta',
    'Sydney - South West'
);
