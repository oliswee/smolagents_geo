"""Query rewriting: synonym expansion for better RAG recall.

When user asks about "医疗设施" (medical facilities), this expands
to "诊所 医院 社区健康中心 医疗服务" to bridge vocabulary gaps
between user language and report text.
"""

# Domain synonym map — tuned for urban planning vocabulary
SYNONYM_MAP = {
    "医疗": ["诊所", "医院", "社区健康中心", "医疗服务", "GP", "clinic", "health", "medical"],
    "诊所": ["医疗中心", "GP诊所", "社区诊所", "clinic", "medical centre"],
    "交通": ["公交", "火车", "轮渡", "站点", "出行", "transport", "transit", "bus", "train"],
    "公交": ["巴士", "公交车", "bus", "公共交通", "transit"],
    "学校": ["中小学", "小学", "中学", "教育机构", "school", "education"],
    "教育": ["学校", "学区", "早教", "中小学", "education", "school"],
    "商业": ["零售", "餐饮", "商铺", "购物", "business", "retail", "shop"],
    "公园": ["绿地", "游乐场", "休闲", "playground", "park", "green space"],
    "安全": ["犯罪", "治安", "crime", "safety"],
    "收入": ["经济", "收入水平", "income", "earnings"],
    "人口": ["居民", "密度", "population", "density"],
}


def expand_query(query: str) -> str:
    """Expand a natural language query with domain synonyms.

    Args:
        query: Original user query in Chinese or English.

    Returns:
        Expanded query string with synonyms appended.
    """
    terms = []
    for keyword, synonyms in SYNONYM_MAP.items():
        if keyword.lower() in query.lower():
            terms.extend(synonyms)

    if not terms:
        return query

    # Deduplicate while preserving order
    seen = set()
    unique_terms = []
    for t in terms:
        if t.lower() not in seen:
            unique_terms.append(t)
            seen.add(t.lower())

    expanded = query + " " + " ".join(unique_terms)
    return expanded
