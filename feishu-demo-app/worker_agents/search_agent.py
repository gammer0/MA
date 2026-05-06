"""外部检索 Agent — 仅公开网页，无权访问飞书企业数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_sdk import SecureAgentClient
from mcp_tools.search_tools import WebSearchTool, PageFetchTool


class SearchAgent(SecureAgentClient):
    """外部检索 Agent — 网页搜索 + 内容抓取"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str):
        super().__init__(agent_id, private_key_pem, gateway_url)
        self._web = WebSearchTool()
        self._fetch = PageFetchTool()

    async def search(self, query: str, task_id: str) -> dict:
        """外部检索。"""
        result = {"query": query}

        await self.call_mcp_tool(
            tool_name="web_search", tool_owner="search_agent",
            tool_args={"query": query}, task_id=task_id,
            reason=f"搜索公开信息",
        )
        result["search"] = await self._web.execute(query)

        await self.call_mcp_tool(
            tool_name="page_fetch", tool_owner="search_agent",
            tool_args={"url": f"https://search.example.com/{query}"}, task_id=task_id,
            reason="获取搜索结果详情",
        )
        result["page"] = await self._fetch.execute(f"https://search.example.com/{query}")

        return result

    async def search_with_violation(self, query: str, task_id: str) -> dict:
        """外部检索 + 越权尝试（用于拦截演示）。"""
        result = await self.search(query, task_id)
        # 越权尝试：访问飞书多维表格（应被 deny）
        try:
            await self.call_mcp_tool(
                tool_name="lark_base", tool_owner="data_agent",
                tool_args={"action": "records", "table_id": query}, task_id=task_id,
                reason="越权尝试：读取飞书多维表格",
            )
            result["violation_detected"] = "ERROR: 越权调用未被拦截！"
        except Exception as e:
            result["violation_detected"] = f"越权拦截成功: {e}"
        return result

