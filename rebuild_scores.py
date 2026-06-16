"""Rebuild the materialized well_resourced_scores table after data import."""
import sys; sys.path.insert(0, ".")
from data_warehouse.connection import DatabaseManager

config = DatabaseManager.get_config_from_credentials()
db = DatabaseManager(config)
engine, conn = db.connect()
raw = conn.connection

print("Rebuilding well_resourced_scores...")
with raw.cursor() as cur:
    # Drop old materialization
    cur.execute("DROP TABLE IF EXISTS public.well_resourced_scores CASCADE")
    # Recreate from view
    cur.execute("CREATE TABLE public.well_resourced_scores AS SELECT * FROM public.well_resourced_scores_view")
    # Add rank columns
    cur.execute("ALTER TABLE public.well_resourced_scores ADD COLUMN rank_overall INTEGER")
    cur.execute("ALTER TABLE public.well_resourced_scores ADD COLUMN rank_business INTEGER")
    cur.execute("ALTER TABLE public.well_resourced_scores ADD COLUMN rank_stops INTEGER")
    cur.execute("ALTER TABLE public.well_resourced_scores ADD COLUMN rank_schools INTEGER")
    cur.execute("ALTER TABLE public.well_resourced_scores ADD COLUMN rank_poi INTEGER")
    # Populate ranks
    cur.execute("UPDATE public.well_resourced_scores w SET rank_overall  = r.rnk FROM (SELECT sa2_code, RANK() OVER (ORDER BY final_score DESC) AS rnk FROM public.well_resourced_scores) r WHERE w.sa2_code = r.sa2_code")
    cur.execute("UPDATE public.well_resourced_scores w SET rank_business = r.rnk FROM (SELECT sa2_code, RANK() OVER (ORDER BY z_business DESC) AS rnk FROM public.well_resourced_scores) r WHERE w.sa2_code = r.sa2_code")
    cur.execute("UPDATE public.well_resourced_scores w SET rank_stops    = r.rnk FROM (SELECT sa2_code, RANK() OVER (ORDER BY z_stops DESC)    AS rnk FROM public.well_resourced_scores) r WHERE w.sa2_code = r.sa2_code")
    cur.execute("UPDATE public.well_resourced_scores w SET rank_schools  = r.rnk FROM (SELECT sa2_code, RANK() OVER (ORDER BY z_schools DESC)  AS rnk FROM public.well_resourced_scores) r WHERE w.sa2_code = r.sa2_code")
    cur.execute("UPDATE public.well_resourced_scores w SET rank_poi      = r.rnk FROM (SELECT sa2_code, RANK() OVER (ORDER BY z_poi DESC)      AS rnk FROM public.well_resourced_scores) r WHERE w.sa2_code = r.sa2_code")
    # Create index
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_sa2_code ON public.well_resourced_scores(sa2_code)")
raw.commit()

# Verify
with raw.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM well_resourced_scores")
    n = cur.fetchone()[0]
    cur.execute("SELECT MIN(final_score), MAX(final_score), AVG(final_score) FROM well_resourced_scores")
    mn, mx, avg = cur.fetchone()
    cur.execute("SELECT sa2_name, final_score, rank_overall FROM well_resourced_scores ORDER BY final_score DESC LIMIT 5")
    top5 = cur.fetchall()

print(f"RAI scores: {n} areas")
print(f"Score range: [{mn:.4f}, {mx:.4f}], Mean: {avg:.4f}")
print("Top 5:")
for t in top5:
    print(f"  {t[0]:30s}  score={t[1]:.4f}  rank={t[2]}")

raw.close()
print("✅ RAI scores rebuilt!")
