"""MCP 工具集 - 统一抽象基类"""
from abc import ABC, abstractmethod


class BaseTool(ABC):
    """
    所有 MCP 工具的统一抽象接口。
    Mock 实现和 MCP 实现都必须遵循此接口，保证切换时功能不漂移。
    """

    tool_name: str       # 工具名称
    tool_owner: str      # "public" | "{agent_id}"
    tool_schema: dict    # JSON Schema（参数定义）

    @abstractmethod
    async def execute(self, **kwargs) -> dict:
        """执行工具。返回统一格式: {"status": "ok", ...} 或 {"status": "error", "message": ...}"""
        ...
