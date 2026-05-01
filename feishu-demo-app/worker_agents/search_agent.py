"""外部检索 Agent — 仅公开网页，无权访问飞书企业数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "agent-sdk"))

from agent_sdk import SecureAgentClient, PermissionDeniedError
from mcp_tools.search_tools import WebSearchTool, PageFetchTool


class SearchAgent(SecureAgentClient):
    """外部检索 Agent — 网页搜索 + 内容抓取"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str):
        super().__init__(agent_id, private_key_pem, gateway_url)
        self._web = WebSearchTool()
        self._fetch = PageFetchTool()

    async def search(self, query: str, task_id: str) -> dict:
        """执行外部检索。演示越权拦截：尝试调用飞书多维表格。"""
        result = {"query": query}

        # 网页搜索
        gate = await self.call_mcp_tool(
            tool_name="web_search", tool_owner="search_agent",
            tool_args={"query": query}, task_id=task_id,
            reason=f"搜索 \"{query[:40]}\" 公开信息",
        )
        result["search"] = await self._web.execute(query)

        # 抓取详情
        gate2 = await self.call_mcp_tool(
            tool_name="page_fetch", tool_owner="search_agent",
            tool_args={"url": f"https://search.example.com/{query}"}, task_id=task_id,
            reason="获取搜索结果详情",
        )
        result["page"] = await self._fetch.execute(f"https://search.example.com/{query}")

        # 演示越权拦截：尝试访问飞书多维表格（应被 deny 阻止）
        await self.call_mcp_tool(
            tool_name="lark_base", tool_owner="data_agent",
            tool_args={"action": "records", "table_id": query}, task_id=task_id,
            reason="越权尝试：读取飞书多维表格",
        )
        result["lark_base_hijack"] = "ERROR: 越权调用未被拦截！"

        return result
