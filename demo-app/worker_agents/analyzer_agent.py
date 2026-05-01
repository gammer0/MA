"""分析器 Agent"""
from typing import Optional
from .base_worker import BaseWorker
from agent_sdk.secure_agent_client import PermissionDeniedError


class AnalyzerAgent(BaseWorker):
    """分析器 Agent — 负责数据分析和图表生成"""

    async def analyze(
        self, data: dict, task_id: str, parent_session_id: Optional[str] = None
    ) -> dict:
        """分析数据。"""
        # 计算（演示正常 MCP 自有工具调用）
        calc_result = await self.call_mcp_tool(
            tool_name="calc",
            tool_owner="analyzer",
            tool_args={"data": data},
            task_id=task_id,
            parent_session_id=parent_session_id,
        )

        # 如果需要补充搜索（演示非编排器 A2A - 场景6）
        if calc_result.get("needs_more_info"):
            try:
                search_result = await self.call_agent(
                    callee_agent_id="searcher",
                    message={"action": "search", "query": calc_result.get("missing_topic", "")},
                    task_id=task_id,
                    parent_session_id=parent_session_id,
                )
                calc_result["supplement"] = search_result
            except PermissionDeniedError as e:
                calc_result["supplement"] = f"[denied] 无法调用 searcher: {e}"

        # 尝试生成图表（演示 deny 硬拒绝 - 场景4）
        try:
            chart = await self.call_mcp_tool(
                tool_name="chart_gen",
                tool_owner="analyzer",
                tool_args={"data": calc_result},
                task_id=task_id,
                parent_session_id=parent_session_id,
            )
            calc_result["chart"] = chart
        except PermissionDeniedError as e:
            calc_result["chart"] = f"[denied] chart_gen 被禁止: {e}"

        return calc_result
