"""Chunk strategy: split each area report by "area + dimension".

Each chunk focuses on ONE specific dimension of ONE specific area,
carrying structured metadata (suburb_name, dimension, score, rank).

This precision-chunking ensures that retrieval matches the user's
concept ("transport", "clinics") rather than diluting in long text.
"""
from typing import List, Dict

# Dimension labels and their corresponding Z-score keys
DIMENSIONS = [
    {
        "key": "z_business",
        "label_cn": "商业活力",
        "label_en": "Commercial Vitality",
        "description": "制造业企业密度、零售餐饮多样性和商业混合度",
        "metric": "businesses_per_1000",
    },
    {
        "key": "z_stops",
        "label_cn": "交通可达性",
        "label_en": "Transport Accessibility",
        "description": "公交站点覆盖率、步行可达面积占比和换乘便利度",
        "metric": "stops_per_capita",
    },
    {
        "key": "z_schools",
        "label_cn": "教育覆盖",
        "label_en": "Education Coverage",
        "description": "中小学及早教中心密度、学区覆盖率和生均资源",
        "metric": "schools_per_1000_youth",
    },
    {
        "key": "z_poi",
        "label_cn": "公共服务",
        "label_en": "Public Services",
        "description": "诊所、社区中心、图书馆等公共服务设施可达性",
        "metric": "poi_per_capita",
    },
]


def chunk_report(report: Dict, include_cross_reference: bool = True) -> List[Dict]:
    """Split one area report into 4 dimension-specific chunks.

    Args:
        report: Output from report_generator.generate_report().
        include_cross_reference: If True, include a sentence referencing
            the area's other dimensions for context.

    Returns:
        List of 4 chunk dicts, each with keys: text, metadata.
    """
    chunks = []
    metadata = report["metadata"]
    sa2_name = report["sa2_name"]
    sa4_name = report.get("sa4_name", "")

    for dim in DIMENSIONS:
        z_value = metadata.get(dim["key"], 0)
        rank_key = f"rank_{dim['key'].replace('z_', '')}"

        # Build dimension-specific chunk text
        lines = [
            f"[{sa2_name}][{dim['label_cn']}]",
            f"区域: {sa2_name} ({sa4_name})",
            f"维度: {dim['label_cn']} ({dim['label_en']})",
            f"指标描述: {dim['description']}",
            f"Z-Score: {z_value:.3f}（与全城均值比较的标准差）",
            f"",
            f"{sa2_name} 的{dim['label_cn']}指数 Z-Score 为 {z_value:.3f}。",
        ]

        # Qualitative interpretation
        if z_value > 1.0:
            lines.append(f"该维度显著高于悉尼均值，属于资源优势维度。")
        elif z_value > 0:
            lines.append(f"该维度略高于悉尼均值。")
        elif z_value > -1.0:
            lines.append(f"该维度低于悉尼均值，存在一定的资源缺口。")
        else:
            lines.append(f"该维度显著低于悉尼均值，是明确的资源短板，需优先关注。")

        if include_cross_reference:
            other_dims = {
                d["label_cn"]: metadata.get(d["key"], 0)
                for d in DIMENSIONS if d["key"] != dim["key"]
            }
            strongest = max(other_dims, key=other_dims.get)
            lines.append(
                f"相比之下，该区域的{strongest}表现更优（Z-Score = {other_dims[strongest]:.2f}），"
                f"呈现'{strongest}好但{dim['label_cn']}不足'的错配特征。"
            )

        chunk_text = "\n".join(lines)

        chunks.append({
            "text": chunk_text,
            "metadata": {
                "suburb_name": sa2_name,
                "sa2_code": report["sa2_code"],
                "sa4_name": sa4_name,
                "dimension": dim["label_cn"],
                "dimension_en": dim["label_en"],
                "z_score": z_value,
                "rank": metadata.get(rank_key, 0),
                "final_score": metadata["final_score"],
            },
        })

    return chunks


def chunk_all_reports(reports: List[Dict]) -> List[Dict]:
    """Chunk all area reports. 109 areas × 4 dimensions = 436 chunks."""
    all_chunks = []
    for report in reports:
        all_chunks.extend(chunk_report(report))
    return all_chunks
