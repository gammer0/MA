"""外部检索 Agent — 仅公开网页，无权访问飞书企业数据"""
from agent_sdk import SecureAgentClient, PermissionDeniedError
from mcp_tools.search_tools import WebSearchTool, PageFetchTool


class SearchAgent(SecureAgentClient):
    """外部检索 Agent — 网页搜索 + 内容抓取"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str):
        super().__init__(agent_id, private_key_pem, gateway_url)
        self._web = WebSearchTool()
        self._fetch = PageFetchTool()

    async def search(self, query: str, task_id: str) -> dict:
        """执行外部检索。"""
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

        return result
