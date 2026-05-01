"""飞书文档助手 (Reporter) — 编排器 Agent"""
from agent_sdk import SecureAgentClient, PermissionDeniedError
from mcp_tools.lark_tools import LarkDocTool


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
            search_result = await self._search_agent.search(instruction, task_id)
            result["external_search"] = search_result
            result["steps"].append({"step": "external_search", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("reporter", "search_agent", "A2A", "denied")
            result["steps"].append({"step": "external_search", "status": "denied", "reason": str(e)})

        # Step 3: 写飞书文档
        try:
            add_trace("reporter", "lark_doc_create", "MCP", "pending")
            report_content = self._build_report(instruction, result)
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
        parts = [f"# 周报: {instruction}\n"]
        parts.append("---\n")

        if result.get("enterprise_data"):
            parts.append("## 📊 企业数据\n")
            ed = result["enterprise_data"]
            if ed.get("calendar"):
                parts.append(f"- 日历: {ed['calendar'].get('data', '无数据')}")
            if ed.get("base_data"):
                parts.append(f"- 多维表格: {ed['base_data'].get('data', '无数据')}")
            parts.append("")

        if result.get("external_search"):
            parts.append("## 🌐 外部动态\n")
            es = result["external_search"]
            if es.get("search"):
                parts.append(f"- 搜索结果: {es['search'].get('results', [])}")
            parts.append("")

        parts.append(f"---\n✅ 报告自动生成")
        return "\n".join(str(p) for p in parts)
