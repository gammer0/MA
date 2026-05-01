"""外部检索工具 — Mock 实现（公开网页搜索）"""


class WebSearchTool:
    """网页搜索工具"""
    tool_name = "web_search"
    description = "从公开网站搜索信息"

    async def execute(self, query: str) -> dict:
        """模拟网页搜索（实际可接入搜索引擎 API）。"""
        return {
            "status": "ok",
            "query": query,
            "results": [
                f"搜索结果1: {query} - 相关技术文档",
                f"搜索结果2: {query} - 行业动态分析",
                f"搜索结果3: {query} - 最新实践指南",
            ]
        }


class PageFetchTool:
    """网页内容抓取工具"""
    tool_name = "page_fetch"
    description = "获取指定网页的详细内容"

    async def execute(self, url: str) -> dict:
        return {
            "status": "ok",
            "url": url,
            "content": f"页面内容摘要: {url} - 包含相关技术细节和案例分析...",
        }
