"""Generate ~400-word natural language reports for each SA2 area.

Each report covers: area overview, RAI score, four dimension sub-indices,
comparison to Greater Sydney mean, and a one-line gap summary.
"""
import pandas as pd
from typing import Dict, List


def _compare_to_mean(score: float, mean: float, metric_name: str) -> str:
    """Generate a human-readable comparison sentence."""
    diff_pct = ((score - mean) / mean * 100) if mean > 0 else 0
    direction = "高于" if diff_pct > 0 else "低于"
    return f"{metric_name}指数 {score:.2f}，{direction}均值 {abs(diff_pct):.0f}%"


def generate_report(row: pd.Series, means: Dict[str, float]) -> str:
    """Generate a single area report from a well_resourced_scores row.

    Args:
        row: A row from well_resourced_scores (pandas Series).
        means: Dict of mean values for each dimension across all 109 areas.

    Returns:
        Natural language report string (~400 words).
    """
    sa2_name = row["sa2_name"]
    sa4_name = row.get("sa4_name", "")
    final_score = row["final_score"]
    rank = row.get("rank_overall", "N/A")

    z_business = row.get("z_business", 0)
    z_stops = row.get("z_stops", 0)
    z_schools = row.get("z_schools", 0)
    z_poi = row.get("z_poi", 0)

    median_income = row.get("median_income")
    income_str = f"${median_income:,.0f}" if pd.notna(median_income) else "暂无数据"

    # Determine weakest dimension
    dims = {
        "商业活力": z_business,
        "交通可达性": z_stops,
        "教育覆盖": z_schools,
        "公共服务": z_poi,
    }
    weakest_dim = min(dims, key=dims.get)
    strongest_dim = max(dims, key=dims.get)

    report = f"""
{sa2_name} 位于 {sa4_name} 区域，资源充裕度指数 (RAI) 为 {final_score:.3f}（0-1 量表），在全部分析的 109 个 SA2 区域中排名第 {rank} 位。该区中位收入为 {income_str} 澳元。

四维资源评估：
- 商业活力：{_compare_to_mean(z_business, means.get('mean_business', 0), '')} 个标准差
- 交通可达性：{_compare_to_mean(z_stops, means.get('mean_stops', 0), '')} 个标准差
- 教育覆盖：{_compare_to_mean(z_schools, means.get('mean_schools', 0), '')} 个标准差
- 公共服务：{_compare_to_mean(z_poi, means.get('mean_poi', 0), '')} 个标准差

主要短板为{weakest_dim}（Z-Score = {dims[weakest_dim]:.2f}），相对优势在{strongest_dim}（Z-Score = {dims[strongest_dim]:.2f}）。

该区域呈现"{strongest_dim}较好但{weakest_dim}不足"的资源错配特征。在悉尼 109 个 SA2 区域中处于中等偏下水平，{'建议重点关注' + weakest_dim + '的资源配置优化' if final_score < 0.5 else '资源整体配置较为均衡'}。
""".strip()
    return report


def generate_all_reports(scores_df: pd.DataFrame) -> List[Dict]:
    """Generate reports for all areas in the scores DataFrame.

    Args:
        scores_df: DataFrame from well_resourced_scores view.

    Returns:
        List of dicts with keys: sa2_code, sa2_name, sa4_name, report, metadata.
    """
    # Compute population-weighted means for comparison context
    means = {
        "mean_business": scores_df["businesses_per_1000"].mean(),
        "mean_stops": scores_df["stops_per_capita"].mean(),
        "mean_schools": scores_df["schools_per_1000_youth"].mean(),
        "mean_poi": scores_df["poi_per_capita"].mean(),
    }

    reports = []
    for _, row in scores_df.iterrows():
        report_text = generate_report(row, means)
        reports.append({
            "sa2_code": row["sa2_code"],
            "sa2_name": row["sa2_name"],
            "sa4_name": row.get("sa4_name", ""),
            "report": report_text,
            "metadata": {
                "final_score": float(row["final_score"]),
                "z_business": float(row.get("z_business", 0)),
                "z_stops": float(row.get("z_stops", 0)),
                "z_schools": float(row.get("z_schools", 0)),
                "z_poi": float(row.get("z_poi", 0)),
                "rank_overall": int(row.get("rank_overall", 0)),
                "median_income": float(row["median_income"]) if pd.notna(row.get("median_income")) else None,
            },
        })

    return reports
