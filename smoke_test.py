"""Smoke test — validates the full pipeline without requiring LLM API.

Run: python smoke_test.py
"""
import sys; sys.path.insert(0, ".")

# ── 1. Config ────────────────────────────────────────
from data_warehouse.connection import DatabaseManager
config = DatabaseManager.get_config_from_credentials()
print("✅ Config loaded")

# ── 2. Database ──────────────────────────────────────
import psycopg2, pandas as pd
db_cfg = config["database"]
raw = psycopg2.connect(host=db_cfg["host"], port=db_cfg["port"], dbname=db_cfg["db_name"],
                        user=db_cfg["user"], password=db_cfg["password"])

tables = ['sa2_regions', 'businesses', 'stopcount', 'schoolcatch', 'popall',
          'incomevalue', 'pollingplaces', 'playgrounds', 'well_resourced_scores']
for t in tables:
    df = pd.read_sql_query(f"SELECT COUNT(*) AS n FROM {t}", raw)
    print(f"  {t:30s} {df['n'][0]:>8,d} rows")
print("✅ Database")

# ── 3. RAI Scores ────────────────────────────────────
df = pd.read_sql_query(
    "SELECT MIN(final_score), MAX(final_score), AVG(final_score), COUNT(*) FROM well_resourced_scores", raw)
mn, mx, avg, n = df.iloc[0]
assert n >= 100, f"Expected >=100 areas, got {n}"
assert mn < mx, "Scores should vary"
print(f"✅ RAI Scores: {n} areas, range [{mn:.3f}, {mx:.3f}], avg={avg:.3f}")

# ── 4. Knowledge Base ────────────────────────────────
from src.rag.vector_store import VectorStore
chroma_cfg = config.get("chromadb", {})
emb_cfg = config.get("embedding", {})
vs = VectorStore(
    persist_directory=chroma_cfg.get("persist_directory", "./chroma_db"),
    collection_name=chroma_cfg.get("collection_name", "suburb_reports"),
    embedding_model=emb_cfg.get("model"),
)
assert vs.count() >= 400, f"Expected >=400 chunks, got {vs.count()}"
print(f"✅ ChromaDB: {vs.count()} chunks")

results = vs.search("Parramatta 医疗设施 诊所", k=3)
assert len(results) >= 1
assert results[0]['similarity'] > 0.4
print(f"✅ Semantic search: top result sim={results[0]['similarity']:.3f}")

# ── 5. Spatial Retriever ─────────────────────────────
from src.rag.retriever import SpatialRetriever
rag_cfg = config.get("rag", {})
retriever = SpatialRetriever(vs, raw, rag_cfg)
result = retriever.retrieve("Parramatta 周边 医疗", top_n=5)
assert len(result['chunks']) >= 1
print(f"✅ Spatial retrieval: {len(result['chunks'])} chunks, {len(result.get('neighbor_areas', []))} neighbors")

# ── 6. Query Rewriter ────────────────────────────────
from src.rag.query_rewriter import expand_query
expanded = expand_query("Parramatta 周边医疗设施不足")
assert len(expanded) > len("Parramatta 周边医疗设施不足")
print(f"✅ Query expansion: added synonyms")

# ── 7. Tool functions (no LLM needed) ────────────────
from src.tools.recommendation_generator import recommendation_generator
rec = recommendation_generator({"gaps": [{
    "suburb": "Test", "final_score": 0.1, "z_scores": {"商业活力": -1.5, "交通可达性": -0.3, "教育覆盖": 0.5, "公共服务": -2.0}, "weakest_dimension": "公共服务"}]}, focus="all")
assert len(rec['recommendations']) >= 2
print(f"✅ recommendation_generator: {len(rec['recommendations'])} recs")

# ── 8. final_answer_checks ───────────────────────────
from src.eval.final_answer_checks import check_has_source_trace, check_no_hallucinated_numbers
assert check_has_source_trace("RAI 评分 0.38，Z-Score -0.5。数据来源：well_resourced_scores")
long_no_source = "这是一个很好的区域，有很多设施。居民们生活便利。交通也很发达。" * 5  # >80 chars, no source
assert not check_has_source_trace(long_no_source)
assert check_no_hallucinated_numbers("RAI 0.5，排名第 50")
assert not check_no_hallucinated_numbers("RAI 1.5，排名 200")
print("✅ Answer checks: all pass")

# ── 9. Session Manager (without agent) ───────────────
from src.session.session_manager import SessionManager
class MockAgent: logs = []
sm = SessionManager(MockAgent())
assert sm.conversation_round == 0
sm.analyzed_areas = ["Parramatta", "Auburn"]
sm.user_preferences = {"focused_dimensions": ["交通可达性"]}
enriched = sm._enrich_message("再分析一下")
assert "Parramatta" in enriched
assert "交通可达性" in enriched
print("✅ SessionManager: context injection works")

raw.close()
print("\n" + "=" * 60)
print("🎉 ALL SMOKE TESTS PASSED!")
print("=" * 60)
print("\nTo run with LLM, set one of:")
print("  $env:ANTHROPIC_API_KEY='sk-ant-...'   # Claude")
print("  $env:DEEPSEEK_API_KEY='sk-...'        # DeepSeek (cheaper)")
print("  $env:OPENAI_API_KEY='sk-...'          # OpenAI")
print("Or start Ollama: ollama serve")
