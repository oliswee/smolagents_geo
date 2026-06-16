"""Multi-turn conversation session manager.

Wraps smolagents CodeAgent to add business-level context tracking:
- Which areas have been analyzed
- Last skill call result summaries
- User preference dimensions

Uses agent.run(msg, reset=False) to preserve smolagents' internal memory
across turns while adding our own higher-level context.
"""
from typing import List, Dict, Optional
from smolagents import CodeAgent


class SessionManager:
    """Manages multi-turn conversations with context persistence."""

    def __init__(self, agent: CodeAgent):
        self.agent = agent
        self.analyzed_areas: List[str] = []
        self.last_results: Dict = {}
        self.user_preferences: Dict = {
            "focused_dimensions": [],
            "favorite_areas": [],
        }
        self.conversation_round: int = 0

    def chat(self, user_message: str) -> str:
        """Process one turn of conversation with context injection.

        Args:
            user_message: Raw user input.

        Returns:
            Agent's natural language response.
        """
        self.conversation_round += 1

        # Inject business context into user message
        enriched = self._enrich_message(user_message)

        # Run agent without resetting memory (preserves ReAct history)
        try:
            result = self.agent.run(enriched, reset=False)
        except Exception as e:
            result = (
                f"分析过程中遇到技术问题: {str(e)}。"
                "请稍后重试或尝试更具体的提问方式。"
            )

        # Update business context from agent logs
        self._extract_context()

        return result

    def _enrich_message(self, user_message: str) -> str:
        """Inject prior analysis context into the user message."""
        parts = [user_message]

        if self.analyzed_areas:
            parts.append(
                f"\n\n[系统上下文] 之前已分析过的区域: {', '.join(self.analyzed_areas)}"
            )

        if self.user_preferences.get("focused_dimensions"):
            parts.append(
                f"用户关注的维度: {', '.join(self.user_preferences['focused_dimensions'])}"
            )

        if self.last_results:
            parts.append(
                f"最近一次分析涉及的区域: {self.last_results.get('areas', 'N/A')}"
            )

        return "".join(parts)

    def _extract_context(self):
        """Extract analyzed areas and skill results from agent.logs."""
        if not hasattr(self.agent, 'logs') or not self.agent.logs:
            return

        areas_seen = set(self.analyzed_areas)

        for step in self.agent.logs:
            # Look for tool calls that involve area parameters
            if hasattr(step, 'tool_calls'):
                for tc in step.tool_calls:
                    args = tc.get('arguments', {})
                    areas = args.get('areas', [])
                    area = args.get('area')
                    if area:
                        areas_seen.add(area)
                    if isinstance(areas, list):
                        areas_seen.update(areas)

        self.analyzed_areas = list(areas_seen)

    def reset(self):
        """Reset session state for a fresh conversation."""
        self.analyzed_areas = []
        self.last_results = {}
        self.conversation_round = 0
        # Note: smolagents' internal memory persists unless agent is recreated.

    def get_context_summary(self) -> str:
        """Return a human-readable summary of the current session context."""
        return (
            f"对话轮次: {self.conversation_round}\n"
            f"已分析区域: {', '.join(self.analyzed_areas) if self.analyzed_areas else '无'}\n"
            f"关注维度: {', '.join(self.user_preferences['focused_dimensions']) if self.user_preferences.get('focused_dimensions') else '全部'}"
        )
