"""企业数据 Agent — 唯一有权访问飞书企业数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_sdk import SecureAgentClient
from mcp_tools.lark_tools import LarkBaseTool, LarkContactTool, LarkCalendarTool


class DataAgent(SecureAgentClient):
    """企业数据 Agent — 飞书通讯录/日历/多维表格"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str):
        super().__init__(agent_id, private_key_pem, gateway_url)
        self._base = LarkBaseTool()
        self._contact = LarkContactTool()
        self._calendar = LarkCalendarTool()

    async def query_enterprise_data(self, query: str, task_id: str) -> dict:
        """查询企业数据：日历、多维表格、通讯录。"""
        result = {"query": query}

        await self.call_mcp_tool(
            tool_name="lark_calendar", tool_owner="data_agent",
            tool_args={"action": "agenda"}, task_id=task_id,
            reason="查询团队最近一周日历",
        )
        result["calendar"] = await self._calendar.execute("agenda")

        await self.call_mcp_tool(
            tool_name="lark_base", tool_owner="data_agent",
            tool_args={"action": "records", "table_id": query}, task_id=task_id,
            reason="查询多维表格项目进度",
        )
        result["base_data"] = await self._base.execute("records", table_id=query)

        await self.call_mcp_tool(
            tool_name="lark_contact", tool_owner="data_agent",
            tool_args={"action": "search", "keyword": query}, task_id=task_id,
            reason="搜索相关人员信息",
        )
        result["contacts"] = await self._contact.execute("search", keyword=query)

        return result

    async def query_calendar_only(self, task_id: str) -> dict:
        """仅查询日历。"""
        await self.call_mcp_tool(
            tool_name="lark_calendar", tool_owner="data_agent",
            tool_args={"action": "agenda"}, task_id=task_id,
            reason="查询团队日历",
        )
        return await self._calendar.execute("agenda")

