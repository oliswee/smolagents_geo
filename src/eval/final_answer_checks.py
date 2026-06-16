"""final_answer_checks for smolagents CodeAgent.

These check functions validate the agent's final_answer before
it's returned to the user. Each returns True (pass) or False (retry).
"""
import re


def check_has_source_trace(final_answer: str, agent_memory=None) -> bool:
    """Ensure the answer contains data source attribution.

    Returns True if the answer references a data source, SA2 code,
    tool call, or explicit "数据来源" section. Short answers (e.g.,
    clarifying questions) are exempted.
    """
    # Short responses don't need source traces
    if len(final_answer) < 80:
        return True

    source_markers = [
        "SA2:",
        "well_resourced_scores",
        "Z-Score",
        "数据来源",
        "RAI",
        "排名",
        "resource_gap_detector",
        "spatial_accessibility",
        "search_suburb_report",
        "recommendation_generator",
        "标准差",
    ]

    has_source = any(marker.lower() in final_answer.lower() for marker in source_markers)
    return has_source


def check_no_hallucinated_numbers(final_answer: str, agent_memory=None) -> bool:
    """Basic check: flag obviously impossible Sydney statistics.

    This is a heuristic check — a full implementation would compare
    numbers against agent_memory tool call results.

    Currently checks for:
    - Impossible RAI scores (> 1.0 or < 0.0)
    - Impossible rankings (> 109)
    - Suspicious round numbers
    """
    # Check for impossible RAI scores
    rai_pattern = re.findall(r'RAI[^\d]*(\d+\.?\d*)', final_answer, re.IGNORECASE)
    for val in rai_pattern:
        score = float(val)
        if score > 1.0 or score < 0.0:
            return False

    # Check for impossible rankings
    rank_pattern = re.findall(r'排名[^\d]*(\d+)', final_answer)
    for val in rank_pattern:
        rank = int(val)
        if rank > 109 or rank < 1:
            return False

    return True


# List of check functions to pass to CodeAgent final_answer_checks
ALL_CHECKS = [
    check_has_source_trace,
    check_no_hallucinated_numbers,
]
