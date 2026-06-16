"""GeoAnalysis Agent — smolagents CodeAgent assembly.

This is the main entry point for the Agent layer. It:
1. Loads configuration
2. Initializes LiteLLMModel (model-agnostic)
3. Registers all @tool functions
4. Connects PostGIS MCP tools via ToolCollection.from_mcp()
5. Assembles the CodeAgent with sandbox execution
6. Provides a run() wrapper with session management
"""
from smolagents import CodeAgent, LiteLLMModel, ToolCollection
from src.config import get_config, get_llm_config
from src.tools.resource_gap_detector import resource_gap_detector
from src.tools.spatial_accessibility import spatial_accessibility_analyzer
from src.tools.recommendation_generator import recommendation_generator
from src.tools.search_suburb_report import search_suburb_report, set_retriever
from src.rag.vector_store import VectorStore
from src.rag.retriever import SpatialRetriever
from src.rag.report_generator import generate_all_reports
from src.rag.chunker import chunk_all_reports

# System prompt addition for hallucination control
SYSTEM_PROMPT_ADDITION = """
你是 GeoAnalysis 城市规划分析助手，专注于悉尼 109 个 SA2 行政区的资源分配分析。

严格遵循以下规则：
1. 所有数值结论必须来自工具调用返回的结构化数据，禁止编造任何数字
2. 每条关键结论必须标注来源（区域报告 chunk 或工具调用 ID）
3. 遇到模糊指代（"东区"、"那几个区"），必须先追问澄清，不得猜测
4. 当检索或工具返回的数据不足时，明确告知用户，不得强行回答
5. 工具选择指南:
   - 问具体区域的评分/排名/短板 → 用 resource_gap_detector（返回精确 Z-Score）
   - 问区域概况/背景/对比 → 用 search_suburb_report（返回文本报告）
   - 问可达性/距离/覆盖 → 用 spatial_accessibility_analyzer
   - 问建议/改进方案 → 用 recommendation_generator
6. 先调用工具获取数据，再回答。不要跳过工具调用直接编造数字。
7. 回答使用中文，但保留关键的英文术语（如 SA2、RAI、Z-Score）
"""


def build_agent(
    config: dict | None = None,
    db_connection=None,
    sandbox_type: str = "local",
) -> CodeAgent:
    """Build and configure the GeoAnalysis CodeAgent."""
    if config is None:
        config = get_config()

    # 1. Model
    llm_cfg = get_llm_config(config)
    model = LiteLLMModel(
        model_id=llm_cfg["model_id"],
        api_key=llm_cfg["api_key"],
        temperature=llm_cfg.get("temperature", 0.1),
        max_tokens=llm_cfg.get("max_tokens", 4096),
    )

    # 2. Tools — business Skills
    custom_tools = [
        resource_gap_detector,
        spatial_accessibility_analyzer,
        recommendation_generator,
        search_suburb_report,
    ]

    # 3. MCP tools
    try:
        mcp_tools = ToolCollection.from_mcp("postgis_mcp_server")
        all_tools = [*custom_tools, *mcp_tools]
    except Exception:
        all_tools = custom_tools

    # 4. Agent type selection: CodeAgent for code-native models,
    #    ToolCallingAgent for chat models (more reliable JSON tool calls)
    agent_cfg = config.get("agent", {})
    model_id = llm_cfg["model_id"].lower()

    # DeepSeek and other chat-first models → ToolCallingAgent (JSON)
    # Claude, Qwen-Coder → CodeAgent (Python code, fewer steps)
    use_code_agent = any(m in model_id for m in ["claude", "coder", "qwen2.5-coder"])

    if use_code_agent:
        _tmp = CodeAgent(tools=[], model=model, add_base_tools=False, max_steps=1)
        default_prompts = dict(_tmp.prompt_templates)
        default_prompts["system_prompt"] = SYSTEM_PROMPT_ADDITION
        agent = CodeAgent(
            tools=all_tools,
            model=model,
            add_base_tools=True,
            max_steps=agent_cfg.get("max_steps", 10),
            prompt_templates=default_prompts,
            additional_authorized_imports=agent_cfg.get("additional_imports", [
                "psycopg2", "pandas", "numpy", "json",
            ]),
            executor_type=sandbox_type or "local",
        )
    else:
        from smolagents import ToolCallingAgent
        agent = ToolCallingAgent(
            tools=all_tools,
            model=model,
            add_base_tools=True,
            max_steps=agent_cfg.get("max_steps", 10),
        )

    return agent


def init_knowledge_base(config: dict, db_conn):
    """Initialize or load the ChromaDB knowledge base.

    Args:
        config: Configuration dict.
        db_conn: SQLAlchemy database connection.

    Returns:
        SpatialRetriever instance ready for search.
    """
    import os.path

    chroma_cfg = config.get("chromadb", {})
    persist_dir = chroma_cfg.get("persist_directory", "./chroma_db")
    collection = chroma_cfg.get("collection_name", "suburb_reports")
    embedding_model = config.get("embedding", {}).get(
        "model", "sentence-transformers/all-MiniLM-L6-v2"
    )

    vs = VectorStore(
        persist_directory=persist_dir,
        collection_name=collection,
        embedding_model=embedding_model,
    )

    # If knowledge base is empty, build it
    if vs.count() == 0:
        print("Knowledge base is empty. Building from database...")
        import pandas as pd

        df = pd.read_sql_query("SELECT * FROM well_resourced_scores", db_conn)
        reports = generate_all_reports(df)
        chunks = chunk_all_reports(reports)
        vs.add_chunks(chunks)
        print(f"Knowledge base built: {vs.count()} chunks")

    # Build retriever
    rag_cfg = config.get("rag", {})
    retriever = SpatialRetriever(vs, db_conn, rag_cfg)

    # Wire retriever into the search tool
    set_retriever(retriever)

    return retriever


def create_agent_with_kb(
    config: dict | None = None,
    db_conn=None,
    sandbox_type: str = "local",
):
    """One-call setup: build agent + initialize knowledge base.

    Returns:
        (agent, retriever) tuple.
    """
    if config is None:
        config = get_config()

    retriever = init_knowledge_base(config, db_conn)
    agent = build_agent(config, db_conn, sandbox_type)

    return agent, retriever
