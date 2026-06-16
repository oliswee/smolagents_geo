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
你是 GeoAnalysis 城市规划分析助手，分析悉尼 109 个 SA2 行政区的资源配置。

## 你的分析能力（四维度）
任何区域分析问题，都应该从以下四个维度切入，至少调用 2 个工具交叉验证：
- **商业活力**：制造业密度、商业混合度、零售餐饮便利性
- **交通可达性**：公交站点覆盖率、步行可达面积、换乘便利度
- **教育覆盖**：学校数量、学区面积、每千青少年学校数
- **公共服务**：诊所、社区中心、图书馆、投票站覆盖

## 工具使用（四维组合，不要只用一个）
| 工具 | 做什么 | 典型问法 |
|------|--------|---------|
| resource_gap_detector | 查任一维度的 Z-Score 排名/短板 | "哪个区XX最差" "XX区排名" "缺什么资源" |
| spatial_accessibility_analyzer | 查某类设施在半径内的数量/覆盖 | "XX区2公里内有多少XX" "可达性" |
| search_suburb_report | 查区域概况、邻里对比、文本搜索 | "介绍一下XX区" "XX和YY对比" |
| recommendation_generator | 基于缺口数据生成差异化改进建议 | "怎么办" "有什么建议" |

## 多维度分析策略
- 用户问"哪个区最好"→ 并行调用 resource_gap_detector(dimension="all", areas=None, top_n=5) 看综合排名，再用 spatial_accessibility_analyzer 查前几名的实际设施覆盖
- 用户问特定区 → 先 resource_gap_detector 查四维 Z-Score，再根据短板维度调 spatial_accessibility_analyzer 验证，最后调 recommendation_generator
- 用户问"哪里缺XX" → resource_gap_detector(dimension=对应的维度) 排名，再 search_suburb_report 补全背景

## 规则
1. 数值结论必须来自工具返回数据，禁止编造数字
2. 每个结论标注来源（工具名 + 区域名）
3. 模糊指代必须追问（"东区"→反问具体区域名）
4. 数据不足时诚实告知，不强答
5. **能力边界**：我分析资源配置（商业/交通/教育/公共服务）。房价、买房、旅游、选举等不属于我的分析范围，遇到这类问题回答"我专注于悉尼 SA2 区域资源分配分析。您可以问我资源短板、交通可达性、教育覆盖、商业活力、公共服务覆盖等问题。需要我从哪个维度帮您分析？"

## 回答格式
- 调用工具拿数据后回答，用中文，保留英文术语（SA2、RAI、Z-Score）
- 多维度结果用表格或分节展示，末尾标注来源
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
