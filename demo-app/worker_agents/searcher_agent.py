"""搜索器 Agent"""
from typing import Optional
from .base_worker import BaseWorker


class SearcherAgent(BaseWorker):
    """搜索器 Agent — 负责搜索和获取网页内容"""

    async def search(
        self, query: str, task_id: str, parent_session_id: Optional[str] = None
    ) -> dict:
        """执行搜索任务。"""
        # 第一步：搜索（演示正常 MCP 自有工具调用 - 场景2）
        search_result = await self.call_mcp_tool(
            tool_name="web_search",
            tool_owner="searcher",
            tool_args={"query": query},
            task_id=task_id,
            parent_session_id=parent_session_id,
        )

        # 第二步：获取第一个结果（演示正常 MCP 自有工具调用）
        if search_result.get("results"):
            page_result = await self.call_mcp_tool(
                tool_name="page_fetch",
                tool_owner="searcher",
                tool_args={"url": search_result["results"][0]},
                task_id=task_id,
                parent_session_id=parent_session_id,
            )
            return {"query": query, "search": search_result, "page": page_result}

        return {"query": query, "search": search_result}
