"""数据分析 Agent — 汇总多源数据、生成图表"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_sdk import SecureAgentClient
from mcp_tools.analyzer_tools import SummarizeTool, ChartGenTool


class AnalyzerAgent(SecureAgentClient):
    """数据分析 Agent — 汇总 + 图表"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str):
        super().__init__(agent_id, private_key_pem, gateway_url)
        self._summarize = SummarizeTool()
        self._chart = ChartGenTool()

    async def analyze(self, task_id: str, enterprise_data: dict = None, search_data: dict = None) -> dict:
        """分析多源数据。"""
        result = {}

        raw = str(enterprise_data or "") + str(search_data or "")

        await self.call_mcp_tool(
            tool_name="data_summarize", tool_owner="analyzer",
            tool_args={"data": raw}, task_id=task_id,
            reason="汇总企业数据与外部检索结果",
        )
        result["summary"] = await self._summarize.execute(raw)

        await self.call_mcp_tool(
            tool_name="chart_gen", tool_owner="analyzer",
            tool_args={"data_type": "柱状图", "content": raw}, task_id=task_id,
            reason="生成数据分析图表",
        )
        result["chart"] = await self._chart.execute("柱状图", raw)

        return result
