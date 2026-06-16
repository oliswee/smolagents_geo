"""RAG Search Tool — wraps the SpatialRetriever as a smolagents @tool.

This is the bridge between the Agent's reasoning loop and the
knowledge base. The Agent calls this tool to get structured report
chunks about specific areas or dimensions.
"""
from smolagents import tool
from typing import Optional


# Global reference set by agent.py during initialization
_retriever = None


def set_retriever(retriever):
    """Set the global retriever instance. Called during agent init."""
    global _retriever
    _retriever = retriever


@tool
def search_suburb_report(
    query: str,
    k: int = 5,
    filter_dimension: Optional[str] = None,
) -> dict:
    """Search the knowledge base for suburb analysis reports. Returns structured
    report chunks with suburb name, dimension, scores, and rankings.
    Use this when the user asks for information about specific areas,
    or when context about area characteristics is needed.
    Use this for questions like 'tell me about Parramatta',
    'what are the strengths of X area', or 'compare X and Y'.

    Args:
        query: Natural language query about suburbs or resources.
               E.g. 'Parramatta 交通 公交 站点' or '哪些区医疗设施不足'.
        k: Number of top results to return. Default 5.
        filter_dimension: Optional dimension filter.
                          One of '商业活力', '交通可达性', '教育覆盖', '公共服务'.
    """
    global _retriever
    if _retriever is None:
        return {
            "error": "retriever_not_initialized",
            "message": "检索器尚未初始化。请检查系统配置。",
            "chunks": [],
        }

    result = _retriever.retrieve(
        query=query,
        top_n=k,
        filter_dimension=filter_dimension,
    )

    # If confidence is low, flag it
    if not _retriever.is_confident(result["max_similarity"]):
        return {
            "status": "low_confidence",
            "message": (
                "当前知识库中针对该问题的信息不足。"
                "建议尝试更具体的区域名称，或联系数据团队补充相关数据。"
            ),
            "chunks": result["chunks"],
            "neighbor_areas": result["neighbor_areas"],
            "max_similarity": result["max_similarity"],
        }

    return {
        "status": "ok",
        "chunks": result["chunks"],
        "neighbor_areas": result["neighbor_areas"],
        "max_similarity": result["max_similarity"],
        "retrieval_method": result["retrieval_method"],
    }
