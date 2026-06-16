"""LLM-as-Eval — lightweight agent quality monitoring.

Periodically samples real user queries and scores Agent responses
across 4 dimensions using an independent low-cost evaluator model.
Low-scoring cases enter a human review queue.
"""
import json
import time
from typing import Dict, List
from pathlib import Path

EVALUATION_DIMENSIONS = {
    "相关性": "回答是否切中用户问题？1-5 分（1=完全跑题, 5=完美匹配）",
    "数值准确性": "回答中的数字是否与硬数据一致？（抽查对比）1-5 分",
    "引用完整性": "每条关键结论是否标注了数据来源？1-5 分",
    "幻觉迹象": "是否存在编造事实或数字的痕迹？（有幻觉=1, 无幻觉=5）",
}

EVAL_PROMPT_TEMPLATE = """你是 Agent 质量评估员。请对以下 Agent 回答进行评分。

[用户问题]
{user_query}

[工具调用返回的硬数据]
{tool_results}

[Agent 最终回答]
{agent_response}

请按以下维度评分 (1-5):
{dimensions}

返回严格的 JSON 格式，不要包含其他文本:
{{"相关性": <score>, "数值准确性": <score>, "引用完整性": <score>, "幻觉迹象": <score>, "总结": "<一句话总结>"}}
"""


class Evaluator:
    """LLM-as-Eval quality monitor."""

    def __init__(
        self,
        evaluator_model_id: str = "deepseek/deepseek-chat",
        alert_threshold: float = 3.0,
        log_dir: str = "./logs/eval",
    ):
        self.evaluator_model_id = evaluator_model_id
        self.alert_threshold = alert_threshold
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._model = None

    @property
    def model(self):
        if self._model is None:
            from smolagents import LiteLLMModel
            self._model = LiteLLMModel(model_id=self.evaluator_model_id)
        return self._model

    def evaluate(
        self,
        user_query: str,
        agent_response: str,
        tool_results: Dict,
    ) -> Dict:
        """Score a single Agent response across 4 dimensions.

        Args:
            user_query: Original user question.
            agent_response: Agent's final answer.
            tool_results: Structured results from tool calls.

        Returns:
            Dict with scores and metadata.
        """
        dims_text = "\n".join(
            f"- {k}: {v}" for k, v in EVALUATION_DIMENSIONS.items()
        )

        prompt = EVAL_PROMPT_TEMPLATE.format(
            user_query=user_query,
            agent_response=agent_response,
            tool_results=json.dumps(tool_results, ensure_ascii=False, indent=2),
            dimensions=dims_text,
        )

        try:
            from smolagents import CodeAgent
            # Use a minimal agent just for structured evaluation
            result_text = self.model(prompt)
            # Try to extract JSON
            # (Simplified — production would use structured output)
            json_start = result_text.find("{")
            json_end = result_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                scores = json.loads(result_text[json_start:json_end])
            else:
                scores = {"error": "Failed to parse evaluator output"}
        except Exception as e:
            scores = {"error": str(e)}

        # Calculate average
        numeric_scores = [
            v for k, v in scores.items()
            if k in EVALUATION_DIMENSIONS and isinstance(v, (int, float))
        ]
        avg_score = sum(numeric_scores) / len(numeric_scores) if numeric_scores else 0

        # Log
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "user_query": user_query,
            "agent_response": agent_response[:500],  # Truncated
            "scores": scores,
            "average": round(avg_score, 2),
            "needs_review": avg_score < self.alert_threshold,
        }

        log_file = self.log_dir / f"eval_{time.strftime('%Y%m%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        return log_entry

    def get_review_queue(self, days: int = 7) -> List[Dict]:
        """Get recent evaluations that need human review."""
        queue = []
        import datetime
        cutoff = time.strftime("%Y%m%d")
        for log_file in self.log_dir.glob("eval_*.jsonl"):
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    if entry.get("needs_review"):
                        queue.append(entry)
        return queue
