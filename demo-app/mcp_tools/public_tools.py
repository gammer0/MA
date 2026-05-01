"""MCP 工具集 - 公共 MCP 池工具 (mock)"""
from .base import BaseTool


class FileReadTool(BaseTool):
    tool_name = "file_read"
    tool_owner = "public"
    tool_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"}
        },
        "required": ["path"],
    }

    async def execute(self, path: str) -> dict:
        return {
            "status": "ok",
            "path": path,
            "content": f"[mock] 文件内容: {path}",
        }


class FileWriteTool(BaseTool):
    tool_name = "file_write"
    tool_owner = "public"
    tool_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "要写入的内容"},
        },
        "required": ["path", "content"],
    }

    async def execute(self, path: str, content: str) -> dict:
        return {
            "status": "ok",
            "path": path,
            "size": len(content),
            "message": f"写入完成: {path}",
        }
