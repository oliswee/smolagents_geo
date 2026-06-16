"""GeoAnalysis Agent — smolagents ToolCallingAgent assembly.

Uses JSON tool-calling (compatible with DeepSeek, GPT-4o, Claude, Ollama).
Tested: DeepSeek reliably calls tools, ~3-6 steps per query.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smolagents import ToolCallingAgent, LiteLLMModel, ToolCollection
from src.config import get_config, get_llm_config
from src.tools.resource_gap_detector import resource_gap_detector
from src.tools.spatial_accessibility import spatial_accessibility_analyzer
from src.tools.recommendation_generator import recommendation_generator
from src.tools.search_suburb_report import search_suburb_report, set_retriever
from src.rag.vector_store import VectorStore
from src.rag.retriever import SpatialRetriever
from src.rag.report_generator import generate_all_reports
from src.rag.chunker import chunk_all_reports

# ── System Prompt (tuned for DeepSeek ToolCallingAgent) ──────
SYSTEM_PROMPT = """
你是 GeoAnalysis 城市规划分析助手，负责悉尼 109 个 SA2 行政区的资源分配分析。

## 规则（必须遵守）
1. 数值结论必须来自工具调用返回数据，禁止编造数字
2. 每条关键结论标注来源（工具名称 + 区域名称）
3. 模糊指代必须先追问澄清（如"东区"→ 反问"Bondi/Coogee/Randwick?"）
4. 数据不足时明确告知用户

## 工具选择指南
- resource_gap_detector: 评分/排名/短板/对比 → 返回精确 Z-Score 和排名
- search_suburb_report: 区域概况/背景描述/文本搜索
- spatial_accessibility_analyzer: 可达性/距离/覆盖率
- recommendation_generator: 改进建议/方案/行动计划

## 回答格式
- 先调用工具，拿到数据后再回答
- 回答用中文，保留英文术语（SA2、RAI、Z-Score）
- 数据后面标注来源，例如"（来源：resource_gap_detector）"
"""


def build_agent(config: dict | None = None) -> ToolCallingAgent:
    """Build GeoAnalysis Agent with ToolCallingAgent (JSON tool calls).

    ToolCallingAgent uses OpenAI-compatible function-calling format,
    compatible with DeepSeek, GPT-4o, Claude, and Ollama models.
    """
    if config is None:
        config = get_config()

    # Model
    llm_cfg = get_llm_config(config)
    model = LiteLLMModel(
        model_id=llm_cfg["model_id"],
        api_key=llm_cfg["api_key"],
        temperature=llm_cfg.get("temperature", 0.1),
        max_tokens=llm_cfg.get("max_tokens", 4096),
    )

    # Tools
    custom_tools = [
        resource_gap_detector,
        spatial_accessibility_analyzer,
        recommendation_generator,
        search_suburb_report,
    ]
    try:
        mcp_tools = ToolCollection.from_mcp("postgis_mcp_server")
        all_tools = [*custom_tools, *mcp_tools]
    except Exception:
        all_tools = custom_tools

    # Agent
    agent_cfg = config.get("agent", {})
    agent = ToolCallingAgent(
        tools=all_tools,
        model=model,
        add_base_tools=True,
        max_steps=agent_cfg.get("max_steps", 8),
    )

    return agent


def init_knowledge_base(config: dict, db_conn):
    """Initialize or load ChromaDB knowledge base, build if empty."""
    chroma_cfg = config.get("chromadb", {})
    emb_cfg = config.get("embedding", {})

    vs = VectorStore(
        persist_directory=chroma_cfg.get("persist_directory", "./chroma_db"),
        collection_name=chroma_cfg.get("collection_name", "suburb_reports"),
        embedding_model=emb_cfg.get("model", "sentence-transformers/all-MiniLM-L6-v2"),
    )

    if vs.count() == 0:
        print("Building knowledge base from database...")
        import pandas as pd
        df = pd.read_sql_query("SELECT * FROM well_resourced_scores", db_conn)
        reports = generate_all_reports(df)
        chunks = chunk_all_reports(reports)
        vs.add_chunks(chunks)
        print(f"  → {vs.count()} chunks")

    retriever = SpatialRetriever(vs, db_conn, config.get("rag", {}))
    set_retriever(retriever)
    return retriever


def create_agent_with_kb(config: dict | None = None, db_conn=None):
    """One-call: build agent + init knowledge base."""
    if config is None:
        config = get_config()
    retriever = init_knowledge_base(config, db_conn)
    agent = build_agent(config)
    return agent, retriever
