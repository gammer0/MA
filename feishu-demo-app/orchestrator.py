"""飞书文档助手 (Reporter) — 编排器 Agent"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_sdk import SecureAgentClient, PermissionDeniedError
from mcp_tools.lark_tools import LarkDocTool
from llm_client import chat


class ReporterAgent(SecureAgentClient):
    """飞书文档助手 Agent — 编排 data_agent + search_agent，写飞书报告"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str,
                 data_agent=None, search_agent=None):
        super().__init__(agent_id, private_key_pem, gateway_url)
        self._data_agent = data_agent
        self._search_agent = search_agent
        self._doc = LarkDocTool()

    @property
    def data_agent_id(self):
        return self._data_agent.agent_id if self._data_agent else ""

    @property
    def search_agent_id(self):
        return self._search_agent.agent_id if self._search_agent else ""

    async def execute_task(self, task_id: str, instruction: str) -> dict:
        """解析指令、委托执行、生成飞书报告。"""
        result = {"task_id": task_id, "instruction": instruction,
                  "steps": [], "trace": [], "report": ""}

        def add_trace(caller, target, call_type, status):
            result["trace"].append({"caller": caller, "target": target,
                                     "call_type": call_type, "status": status})

        # Step 1: 委托企业数据 Agent
        try:
            add_trace("reporter", "data_agent", "A2A", "pending")
            await self.call_agent(
                callee_agent_id=self.data_agent_id,
                message={"action": "query", "query": instruction},
                task_id=task_id,
                reason="查询企业数据（日历/通讯录/多维表格）",
            )
            add_trace("reporter", "data_agent", "A2A", "allowed")
            data_result = await self._data_agent.query_enterprise_data(instruction, task_id)
            result["enterprise_data"] = data_result
            result["steps"].append({"step": "enterprise_data", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("reporter", "data_agent", "A2A", "denied")
            result["steps"].append({"step": "enterprise_data", "status": "denied", "reason": str(e)})

        # Step 2: 委托外部检索 Agent
        try:
            add_trace("reporter", "search_agent", "A2A", "pending")
            await self.call_agent(
                callee_agent_id=self.search_agent_id,
                message={"action": "search", "query": instruction},
                task_id=task_id,
                reason="搜索外部行业动态和公开信息",
            )
            add_trace("reporter", "search_agent", "A2A", "allowed")
            try:
                search_result = await self._search_agent.search(instruction, task_id)
            except PermissionDeniedError as e:
                # search_agent 内部 MCP 调用被 deny（越权拦截演示）
                add_trace("search_agent", "lark_base", "MCP", "denied")
                result["security_events"] = [{
                    "event": "越权拦截",
                    "detail": "search_agent 尝试调用 lark_base (飞书多维表格) 被 deny 令牌阻止",
                    "result": str(e)
                }]
                # 继续执行——用部分结果
                search_result = {"query": instruction, "search": {"status": "ok"}, "lark_base_hijack": f"[denied] {e}"}
            result["external_search"] = search_result
            result["steps"].append({"step": "external_search", "status": "ok"})
            if search_result.get("lark_base_hijack") and "denied" in str(search_result["lark_base_hijack"]).lower():
                if not result.get("security_events"):
                    result["security_events"] = [{
                        "event": "越权拦截",
                        "detail": "search_agent 尝试调用 lark_base (飞书多维表格) 被 deny 令牌阻止",
                        "result": search_result["lark_base_hijack"]
                    }]
        except PermissionDeniedError as e:
            add_trace("reporter", "search_agent", "A2A", "denied")
            result["steps"].append({"step": "external_search", "status": "denied", "reason": str(e)})

        # Step 3: 用 LLM 生成报告并写入飞书文档
        try:
            add_trace("reporter", "lark_doc_create", "MCP", "pending")
            report_content = await self._generate_report_async(instruction, result)
            await self.call_mcp_tool(
                tool_name="lark_doc", tool_owner="reporter",
                tool_args={"action": "create", "title": f"周报: {instruction[:30]}",
                           "content": report_content},
                task_id=task_id,
                reason="生成周报并写入飞书文档",
            )
            add_trace("reporter", "lark_doc_create", "MCP", "allowed")
            doc_result = await self._doc.execute("create", title=f"周报: {instruction[:30]}",
                                                  content=report_content)
            result["report"] = doc_result
            result["steps"].append({"step": "write_report", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("reporter", "lark_doc_create", "MCP", "denied")
            result["steps"].append({"step": "write_report", "status": "denied", "reason": str(e)})

        await self.finalize_task(task_id)
        return result

    def _build_report(self, instruction: str, result: dict) -> str:
        """使用 LLM 生成结构化报告。"""
        # 注：_build_report 是同步方法，LLM 调用在外部用同步方式
        data_summary = ""
        if result.get("enterprise_data"):
            ed = result["enterprise_data"]
            data_summary += f"日历数据: {ed.get('calendar', '无')}\n"
            data_summary += f"多维表格: {ed.get('base_data', '无')}\n"
        if result.get("external_search"):
            es = result["external_search"]
            data_summary += f"搜索结果: {es.get('search', '无')}\n"

        return f"# 周报: {instruction}\n\n## 企业数据\n{data_summary}\n\n## 外部动态\n待补充"

    async def _generate_report_async(self, instruction: str, result: dict) -> str:
        """异步 LLM 生成报告。"""
        data_summary = ""
        if result.get("enterprise_data"):
            ed = result["enterprise_data"]
            data_summary += f"日历: {ed.get('calendar', '无')}\n"
            data_summary += f"多维表格: {ed.get('base_data', '无')}\n"
        if result.get("external_search"):
            es = result["external_search"]
            data_summary += f"搜索: {es.get('search', '无')}\n"

        prompt = f"基于以下数据生成一篇企业周报（Markdown，100字内，用中文）:\n任务: {instruction}\n\n{data_summary}"
        try:
            return await chat(prompt, system="你是飞书文档助手，负责生成企业周报。")
        except Exception:
            return self._build_report(instruction, result)
