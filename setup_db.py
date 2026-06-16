"""One-shot database setup: drop existing → create schema → views → indexes."""
import sys
sys.path.insert(0, ".")

from data_warehouse.connection import DatabaseManager
import pandas as pd

config = DatabaseManager.get_config_from_credentials()

db = DatabaseManager(config)
engine, conn = db.connect()
raw = conn.connection

# ── Drop all user objects ──────────────────────────────────
with raw.cursor() as cur:
    # Drop tables (skip postgis extension tables)
    cur.execute("""
        DO $$ DECLARE r RECORD;
        BEGIN
            FOR r IN (
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename NOT IN ('spatial_ref_sys', 'geography_columns',
                                        'geometry_columns', 'raster_columns',
                                        'raster_overviews')
            ) LOOP
                EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """)
    # Drop views (skip PostGIS/internal views)
    cur.execute("""
        DO $$ DECLARE r RECORD;
        BEGIN
            FOR r IN (
                SELECT viewname FROM pg_views
                WHERE schemaname = 'public'
                  AND viewname NOT IN ('geography_columns', 'geometry_columns',
                                       'raster_columns', 'raster_overviews')
            )
            LOOP
                EXECUTE 'DROP VIEW IF EXISTS public.' || quote_ident(r.viewname) || ' CASCADE';
            END LOOP;
        END $$;
    """)
    cur.execute("DROP FUNCTION IF EXISTS public.sigmoid CASCADE")
raw.commit()
print("All user objects dropped.")

# ── Execute DDL files ──────────────────────────────────────
for f in ["data_warehouse/schema.sql", "data_warehouse/views.sql", "data_warehouse/indexes.sql"]:
    db.execute_ddl(conn, f)

# ── Verify ─────────────────────────────────────────────────
with raw.cursor() as cur:
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_type='BASE TABLE'
        ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]

    cur.execute("""
        SELECT table_name FROM information_schema.views
        WHERE table_schema='public' ORDER BY table_name
    """)
    views = [r[0] for r in cur.fetchall()]

print(f"\nTables ({len(tables)}):")
for t in tables:
    with raw.cursor() as cur2:
        cur2.execute(f'SELECT COUNT(*) FROM "{t}"')
        cnt = cur2.fetchone()[0]
    print(f"  - {t}  ({cnt} rows)")

print(f"\nViews ({len(views)}):")
for v in views:
    print(f"  - {v}")

raw.close()
print("\n✅ Database setup complete!")
