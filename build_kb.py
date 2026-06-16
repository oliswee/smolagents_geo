"""Build ChromaDB knowledge base from well_resourced_scores data."""
import sys; sys.path.insert(0, ".")

import pandas as pd
from data_warehouse.connection import DatabaseManager
from src.rag.report_generator import generate_all_reports
from src.rag.chunker import chunk_all_reports
from src.rag.vector_store import VectorStore
from src.rag.retriever import SpatialRetriever
from src.tools.search_suburb_report import set_retriever

# Read DB credentials from Credentials.json
config = DatabaseManager.get_config_from_credentials()
import os; os.environ["DB_PASSWORD"] = config["database"]["password"]

# 1. Connect to DB and load scores
import psycopg2
db_mgr = DatabaseManager(config)
engine, conn = db_mgr.connect()
raw_pg = conn.connection  # raw psycopg2 connection for pandas 3.x compat
df = pd.read_sql_query("SELECT * FROM well_resourced_scores ORDER BY sa2_name", raw_pg)
print(f"Loaded {len(df)} areas from well_resourced_scores")

# 2. Generate reports
reports = generate_all_reports(df)
print(f"Generated {len(reports)} reports")

# 3. Chunk
chunks = chunk_all_reports(reports)
print(f"Created {len(chunks)} chunks ({len(chunks)/len(reports):.0f} per area)")

# 4. Embed and store in ChromaDB
chroma_cfg = config.get("chromadb", {})
emb_cfg = config.get("embedding", {})
vs = VectorStore(
    persist_directory=chroma_cfg.get("persist_directory", "./chroma_db"),
    collection_name=chroma_cfg.get("collection_name", "suburb_reports"),
    embedding_model=emb_cfg.get("model", "sentence-transformers/all-MiniLM-L6-v2"),
)
n = vs.add_chunks(chunks)
print(f"Stored {n} chunks in ChromaDB")

# 5. Test search
results = vs.search("Parramatta 诊所 医疗设施", k=3)
print("\nTest search results:")
for i, r in enumerate(results):
    print(f"  [{i+1}] {r['metadata']['suburb_name']} | {r['metadata']['dimension']} | sim={r['similarity']:.3f}")

# 6. Wire up retriever
rag_cfg = config.get("rag", {})
retriever = SpatialRetriever(vs, raw_pg, rag_cfg)  # pass raw psycopg2 conn for pandas 3.x
set_retriever(retriever)

# 7. Test spatial retrieval
result = retriever.retrieve("Parramatta 周边 医疗", top_n=5)
print(f"\nSpatial retrieval test:")
print(f"  Neighbors: {result['neighbor_areas']}")
print(f"  Chunks: {len(result['chunks'])}")
print(f"  Max similarity: {result['max_similarity']:.3f}")
print(f"  Method: {result['retrieval_method']}")

conn.close()
print("\n✅ Knowledge base built and verified!")
