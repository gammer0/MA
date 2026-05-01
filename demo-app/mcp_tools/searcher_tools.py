"""MCP 工具集 - 搜索器自有工具 (mock)"""
from .base import BaseTool


class WebSearchTool(BaseTool):
    tool_name = "web_search"
    tool_owner = "searcher"
    tool_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"}
        },
        "required": ["query"],
    }

    async def execute(self, query: str) -> dict:
        return {
            "status": "ok",
            "results": [
                f"[mock] 关于 '{query}' 的搜索结果 - 链接1",
                f"[mock] 关于 '{query}' 的搜索结果 - 链接2",
                f"[mock] 关于 '{query}' 的搜索结果 - 链接3",
            ],
        }


class PageFetchTool(BaseTool):
    tool_name = "page_fetch"
    tool_owner = "searcher"
    tool_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要获取的网页URL"}
        },
        "required": ["url"],
    }

    async def execute(self, url: str) -> dict:
        return {
            "status": "ok",
            "url": url,
            "content": f"[mock] 从 {url} 获取的网页内容...\n\n这是关于搜索主题的详细信息。",
        }
