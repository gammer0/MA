"""企业数据 Agent — 唯一有权访问飞书企业数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "agent-sdk"))

from agent_sdk import SecureAgentClient, PermissionDeniedError
from mcp_tools.lark_tools import LarkBaseTool, LarkContactTool, LarkCalendarTool


class DataAgent(SecureAgentClient):
    """企业数据 Agent — 飞书通讯录/日历/多维表格"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str):
        super().__init__(agent_id, private_key_pem, gateway_url)
        self._base = LarkBaseTool()
        self._contact = LarkContactTool()
        self._calendar = LarkCalendarTool()

    async def query_enterprise_data(self, query: str, task_id: str) -> dict:
        """根据需求查询企业数据。"""
        result = {"query": query}

        # 日历查询（飞书 CLI）
        gate = await self.call_mcp_tool(
            tool_name="lark_calendar", tool_owner="data_agent",
            tool_args={"action": "agenda", "days": 7}, task_id=task_id,
            reason="查询团队最近一周日历",
        )
        result["calendar"] = await self._calendar.execute("agenda", days=7)

        # 多维表格查询（飞书 CLI）
        gate2 = await self.call_mcp_tool(
            tool_name="lark_base", tool_owner="data_agent",
            tool_args={"action": "records", "table_id": query}, task_id=task_id,
            reason="查询多维表格项目进度",
        )
        result["base_data"] = await self._base.execute("records", table_id=query)

        # 通讯录搜索（飞书 CLI）
        gate3 = await self.call_mcp_tool(
            tool_name="lark_contact", tool_owner="data_agent",
            tool_args={"action": "search", "keyword": query}, task_id=task_id,
            reason="搜索相关人员信息",
        )
        result["contacts"] = await self._contact.execute("search", keyword=query)

        return result
