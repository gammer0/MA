"""MCP 工具集 - 分析器自有工具 (mock)"""
from .base import BaseTool


class CalcTool(BaseTool):
    tool_name = "calc"
    tool_owner = "analyzer"
    tool_schema = {
        "type": "object",
        "properties": {
            "data": {"type": "object", "description": "要计算的数据"}
        },
        "required": ["data"],
    }

    async def execute(self, data: dict) -> dict:
        return {
            "status": "ok",
            "analysis": "[mock] 数据分析结果: 趋势向上，增长率 15%",
            "needs_more_info": False,
            "missing_topic": "",
        }


class ChartGenTool(BaseTool):
    tool_name = "chart_gen"
    tool_owner = "analyzer"
    tool_schema = {
        "type": "object",
        "properties": {
            "data": {"type": "object", "description": "图表数据"}
        },
        "required": ["data"],
    }

    async def execute(self, data: dict) -> dict:
        return {
            "status": "ok",
            "chart_type": "bar",
            "chart_data": "[mock] 柱状图数据...",
            "message": "图表生成完成",
        }
