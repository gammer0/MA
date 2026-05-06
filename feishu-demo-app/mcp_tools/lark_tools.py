"""飞书 MCP 工具 — 封装 lark-cli 命令"""

import subprocess
import json
import shlex


class LarkToolBase:
    """飞书 CLI 工具基类。通过 subprocess 调用 lark-cli。"""

    def _run(self, *args) -> dict:
        """执行 lark-cli 命令并返回 JSON 结果。"""
        cmd = ["lark-cli"] + list(args)
        # 默认输出格式为 json（lark-cli 默认已经是 json）
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                return {"status": "ok", "data": json.loads(result.stdout)}
            return {"status": "error", "stderr": result.stderr.strip(), "stdout": result.stdout.strip()}
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "命令超时"}
        except FileNotFoundError:
            return {"status": "error", "message": "lark-cli 未安装"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class LarkDocTool(LarkToolBase):
    """飞书文档工具"""
    tool_name = "lark_doc"
    description = "创建/读取/更新飞书云文档"

    async def execute(self, action: str, title: str = "", content: str = "", doc_id: str = "") -> dict:
        if action == "create":
            return self._run("docs", "+create", "--title", title, "--content", content)
        elif action == "read":
            return self._run("docs", "+fetch", "--doc-id", doc_id)
        return {"status": "error", "message": f"未知操作: {action}"}


class LarkBaseTool(LarkToolBase):
    """飞书多维表格工具"""
    tool_name = "lark_base"
    description = "查询/操作飞书多维表格数据"

    async def execute(self, action: str, table_id: str = "", view_id: str = "") -> dict:
        if action == "records":
            return self._run("base", "+record-list", "--table-id", table_id)
        elif action == "fields":
            return self._run("base", "+field-list", "--table-id", table_id)
        return {"status": "error", "message": f"未知操作: {action}"}


class LarkContactTool(LarkToolBase):
    """飞书通讯录工具"""
    tool_name = "lark_contact"
    description = "搜索飞书通讯录用户"

    async def execute(self, action: str, keyword: str = "") -> dict:
        if action == "search":
            return self._run("contact", "+search-user", "--query", keyword)
        return {"status": "error", "message": f"未知操作: {action}"}


class LarkCalendarTool(LarkToolBase):
    """飞书日历工具"""
    tool_name = "lark_calendar"
    description = "查看飞书日历日程"

    async def execute(self, action: str, days: int = 7) -> dict:
        if action == "agenda":
            return self._run("calendar", "+agenda")
        return {"status": "error", "message": f"未知操作: {action}"}
