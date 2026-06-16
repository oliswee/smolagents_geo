"""Skill 3: Recommendation Generator.

Generates differentiated resource allocation recommendations based on
gap analysis results. Uses rule templates + natural language polish.
"""
from smolagents import tool


# Rule-based recommendation templates by dimension
RECOMMENDATION_TEMPLATES = {
    "商业活力": [
        {
            "action": "引入社区零售孵化计划",
            "rationale": "降低小商户准入门槛，提供前6个月租金补贴",
            "expected_impact": "预计 12 个月内新增 15-20 家社区商铺",
        },
        {
            "action": "优化商业混合度",
            "rationale": "引入餐饮、生鲜、日杂等多业态组合，提升香农多样性指数",
            "expected_impact": "商业混合度指数提升 0.1-0.2",
        },
        {
            "action": "设立周末市集/流动商铺",
            "rationale": "利用公共空间在周末举办市集，测试商业需求",
            "expected_impact": "低成本验证商业潜力，3 个月内可启动",
        },
    ],
    "交通可达性": [
        {
            "action": "增加社区公交支线",
            "rationale": "加密支线巴士班次，缩短步行到站距离至 400m 以内",
            "expected_impact": "公交 500m 步行覆盖率提升 15-20%",
        },
        {
            "action": "优化步行和骑行连接",
            "rationale": "建设步行绿道和共享单车停放点，改善最后一公里连接",
            "expected_impact": "步行可达范围内的设施数量增加 30%",
        },
        {
            "action": "设立社区接驳服务",
            "rationale": "在公交稀疏区域设立 on-demand 接驳小巴",
            "expected_impact": "老年人等出行弱势群体交通可达性显著改善",
        },
    ],
    "教育覆盖": [
        {
            "action": "增设早教中心和课后托管",
            "rationale": "在年轻家庭密集但早教资源不足的区域优先配置",
            "expected_impact": "每千青少年学校数提升至接近均值水平",
        },
        {
            "action": "优化现有学校学区边界",
            "rationale": "调整学区划分使更多家庭步行可达学校",
            "expected_impact": "学区覆盖率提升 10-15%",
        },
        {
            "action": "引入流动教育资源",
            "rationale": "设立移动图书馆和学习中心，定期巡回服务",
            "expected_impact": "短期低成本补充教育覆盖",
        },
    ],
    "公共服务": [
        {
            "action": "设立社区健康中心",
            "rationale": "在诊所密度低的区域新建或改造现有建筑为健康中心",
            "expected_impact": "千人诊所数提升至全城均值的 80%",
        },
        {
            "action": "引入移动诊所/远程医疗",
            "rationale": "在设施建设期间先用移动诊所和 telehealth 弥补缺口",
            "expected_impact": "立即提升服务覆盖率，无需等待基建",
        },
        {
            "action": "共享社区空间",
            "rationale": "将现有社区中心改造为多功能空间（图书馆+诊所+活动中心）",
            "expected_impact": "空间利用率提升，降低单独建设成本",
        },
    ],
}


@tool
def recommendation_generator(
    gap_analysis: dict,
    focus: str = "all",
) -> dict:
    """Generate differentiated resource allocation recommendations based on
    gap analysis and spatial accessibility results.
    Use this when the user asks 'what should we do', 'recommendations',
    'how to improve', 'action plan', or 'what are the solutions'.

    Args:
        gap_analysis: Structured result from resource_gap_detector.
                      Must contain 'gaps' key with list of areas and their scores.
        focus: Recommendation focus area.
               One of '交通微循环', '公共服务优化', '商业活力触达', or 'all'.
    """
    if not gap_analysis or "gaps" not in gap_analysis:
        return {
            "error": "invalid_input",
            "message": "请先运行 resource_gap_detector 获取资源缺口数据。",
        }

    focus_dim_map = {
        "交通微循环": "交通可达性",
        "公共服务优化": "公共服务",
        "商业活力触达": "商业活力",
        # "教育覆盖" → "教育均衡"
    }

    target_dim = focus_dim_map.get(focus)

    recommendations = []
    for area_gap in gap_analysis.get("gaps", []):
        suburb = area_gap["suburb"]

        # Determine which dimension(s) to recommend for
        if target_dim:
            dims_to_fix = [target_dim]
        else:
            # Fix the weakest dimension
            dims_to_fix = [area_gap.get("weakest_dimension", "公共服务")]
            # Also include second-weakest if it's also below -0.5
            z_scores = area_gap.get("z_scores", {})
            sorted_dims = sorted(z_scores.items(), key=lambda x: x[1])
            if len(sorted_dims) >= 2 and sorted_dims[1][1] < -0.5:
                dims_to_fix.append(sorted_dims[1][0])

        area_recs = []
        priority = 1
        for dim in dims_to_fix:
            templates = RECOMMENDATION_TEMPLATES.get(dim, [])
            for tpl in templates[:2]:  # Top 2 per dimension
                area_recs.append({
                    "priority": priority,
                    "area": suburb,
                    "dimension": dim,
                    "action": tpl["action"],
                    "rationale": tpl["rationale"],
                    "expected_impact": tpl["expected_impact"],
                })
                priority += 1

        recommendations.extend(area_recs)

    return {
        "recommendations": recommendations,
        "focus": focus,
        "total_actions": len(recommendations),
        "disclaimer": (
            "以上建议基于 RAI 资源评价体系的定量分析生成。"
            "具体实施方案需结合实地调研、社区听证和预算评估。"
        ),
    }
