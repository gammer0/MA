"""飞书文档助手 (Reporter) — 多场景硬编码编排器

支持三种演示场景：
  场景A(默认) - 三Agent正常委托（reporter → data_agent + search_agent → 写文档）
  场景B(越权) - 三Agent越权拦截（search_agent 尝试调 lark_base 被 deny 阻止）
  场景C(分析) - 单链四Agent调用（reporter → data_agent → search_agent → analyzer → 写文档）

指令路由：
  - 包含「越权」→ 场景B
  - 包含「分析」或「四Agent」→ 场景C
  - 默认 → 场景A
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_sdk import SecureAgentClient, PermissionDeniedError
from mcp_tools.lark_tools import LarkDocTool
from llm_client import chat


class ReporterAgent(SecureAgentClient):
    """多场景编排器 — 硬编码三种调用链"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str,
                 data_agent=None, search_agent=None, analyzer_agent=None):
        super().__init__(agent_id, private_key_pem, gateway_url)
        self._data_agent = data_agent
        self._search_agent = search_agent
        self._analyzer_agent = analyzer_agent
        self._doc = LarkDocTool()

    @property
    def data_agent_id(self):
        return self._data_agent.agent_id if self._data_agent else ""

    @property
    def search_agent_id(self):
        return self._search_agent.agent_id if self._search_agent else ""

    @property
    def analyzer_agent_id(self):
        return self._analyzer_agent.agent_id if self._analyzer_agent else ""

    def _detect_scenario(self, instruction: str) -> str:
        low = instruction.lower()
        if "越权" in low or "拦截" in low:
            return "violation"
        if ("四" in low and ("agent" in low)) or "分析" in low:
            return "multi"
        return "normal"

    async def execute_task(self, task_id: str, instruction: str) -> dict:
        scenario = self._detect_scenario(instruction)
        if scenario == "violation":
            return await self._run_violation(task_id, instruction)
        elif scenario == "multi":
            return await self._run_multi_agent(task_id, instruction)
        return await self._run_normal(task_id, instruction)

    # ================================================================
    # 场景A：三Agent正常委托
    # ================================================================
    async def _run_normal(self, task_id: str, instruction: str) -> dict:
        result = {"scenario": "三Agent正常委托", "task_id": task_id,
                  "instruction": instruction, "steps": [], "trace": [],
                  "security_events": [], "report": ""}

        def add_trace(caller, target, ct, status):
            result["trace"].append({"caller": caller, "target": target,
                                     "call_type": ct, "status": status})

        # Step 1: data_agent
        try:
            add_trace("reporter", "data_agent", "A2A", "pending")
            await self.call_agent(
                callee_agent_id=self.data_agent_id,
                message={"action": "query", "query": instruction},
                task_id=task_id, reason="查询企业数据（日历/通讯录/多维表格）",
            )
            add_trace("reporter", "data_agent", "A2A", "allowed")
            result["enterprise_data"] = await self._data_agent.query_enterprise_data(instruction, task_id)
            result["steps"].append({"step": "查询企业数据", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("reporter", "data_agent", "A2A", "denied")
            result["steps"].append({"step": "查询企业数据", "status": "denied", "reason": str(e)})

        # Step 2: search_agent
        try:
            add_trace("reporter", "search_agent", "A2A", "pending")
            await self.call_agent(
                callee_agent_id=self.search_agent_id,
                message={"action": "search", "query": instruction},
                task_id=task_id, reason="搜索外部行业动态和公开信息",
            )
            add_trace("reporter", "search_agent", "A2A", "allowed")
            result["external_search"] = await self._search_agent.search(instruction, task_id)
            result["steps"].append({"step": "搜索外部信息", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("reporter", "search_agent", "A2A", "denied")
            result["steps"].append({"step": "搜索外部信息", "status": "denied", "reason": str(e)})

        # Step 3: lark_doc
        try:
            add_trace("reporter", "lark_doc", "MCP", "pending")
            report_content = await self._build_report(instruction, result)
            await self.call_mcp_tool(
                tool_name="lark_doc", tool_owner="reporter",
                tool_args={"action": "create", "title": f"周报: {instruction[:30]}",
                           "content": report_content},
                task_id=task_id, reason="生成报告并写入飞书文档",
            )
            add_trace("reporter", "lark_doc", "MCP", "allowed")
            result["report"] = await self._doc.execute(
                "create", title=f"周报: {instruction[:30]}", content=report_content)
            result["steps"].append({"step": "写入飞书文档", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("reporter", "lark_doc", "MCP", "denied")
            result["steps"].append({"step": "写入飞书文档", "status": "denied", "reason": str(e)})

        result["summary"] = await self._gen_summary(instruction, result)
        await self.finalize_task(task_id)
        return result

    # ================================================================
    # 场景B：三Agent越权拦截
    # ================================================================
    async def _run_violation(self, task_id: str, instruction: str) -> dict:
        result = {"scenario": "三Agent越权拦截演示", "task_id": task_id,
                  "instruction": instruction, "steps": [], "trace": [],
                  "security_events": [], "report": ""}

        def add_trace(caller, target, ct, status):
            result["trace"].append({"caller": caller, "target": target,
                                     "call_type": ct, "status": status})

        try:
            add_trace("reporter", "data_agent", "A2A", "pending")
            await self.call_agent(
                callee_agent_id=self.data_agent_id,
                message={"action": "query", "query": instruction},
                task_id=task_id, reason="查询企业数据",
            )
            add_trace("reporter", "data_agent", "A2A", "allowed")
            result["enterprise_data"] = await self._data_agent.query_enterprise_data(instruction, task_id)
            result["steps"].append({"step": "查询企业数据", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("reporter", "data_agent", "A2A", "denied")
            result["steps"].append({"step": "查询企业数据", "status": "denied"})

        try:
            add_trace("reporter", "search_agent", "A2A", "pending")
            await self.call_agent(
                callee_agent_id=self.search_agent_id,
                message={"action": "search_with_violation", "query": instruction},
                task_id=task_id, reason="搜索外部数据（包含越权尝试）",
            )
            add_trace("reporter", "search_agent", "A2A", "allowed")
            try:
                search_result = await self._search_agent.search_with_violation(instruction, task_id)
                violation_msg = search_result.get("violation_detected", "")
                if "拦截成功" in str(violation_msg):
                    add_trace("search_agent", "lark_base", "MCP", "denied")
                    result["security_events"].append({
                        "event": "越权拦截",
                        "detail": "search_agent 尝试调用 lark_base (飞书多维表格) 被 deny 令牌阻止",
                    })
                result["external_search"] = search_result
            except PermissionDeniedError as e:
                add_trace("search_agent", "lark_base", "MCP", "denied")
                result["security_events"].append({
                    "event": "越权拦截",
                    "detail": "search_agent 尝试调用 lark_base (飞书多维表格) 被 deny 令牌阻止",
                })
                result["external_search"] = {"violation_detected": f"越权拦截成功: {e}"}
            result["steps"].append({"step": "搜索外部信息（含越权拦截）", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("reporter", "search_agent", "A2A", "denied")
            result["steps"].append({"step": "搜索外部信息", "status": "denied"})

        try:
            add_trace("reporter", "lark_doc", "MCP", "pending")
            events_text = "; ".join(e["detail"] for e in result.get("security_events", []))
            content = f"# 越权拦截演示报告\n\n## 安全事件\n{events_text}\n\n## 结论\n权限系统成功拦截了search_agent对飞书企业数据的越权访问。"
            await self.call_mcp_tool(
                tool_name="lark_doc", tool_owner="reporter",
                tool_args={"action": "create", "title": "越权拦截演示报告", "content": content},
                task_id=task_id, reason="生成越权拦截演示报告",
            )
            add_trace("reporter", "lark_doc", "MCP", "allowed")
            result["report"] = await self._doc.execute("create", title="越权拦截演示报告", content=content)
            result["steps"].append({"step": "写入飞书文档", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("reporter", "lark_doc", "MCP", "denied")
            result["steps"].append({"step": "写入飞书文档", "status": "denied"})

        result["summary"] = await self._gen_summary(instruction, result)
        await self.finalize_task(task_id)
        return result

    # ================================================================
    # 场景C：单链四Agent调用
    # ================================================================
    async def _run_multi_agent(self, task_id: str, instruction: str) -> dict:
        result = {"scenario": "单链四Agent调用", "task_id": task_id,
                  "instruction": instruction, "steps": [], "trace": [],
                  "security_events": [], "report": ""}

        def add_trace(caller, target, ct, status):
            result["trace"].append({"caller": caller, "target": target,
                                     "call_type": ct, "status": status})

        enterprise_data = None
        search_data = None

        try:
            add_trace("reporter", "data_agent", "A2A", "pending")
            await self.call_agent(
                callee_agent_id=self.data_agent_id,
                message={"action": "query", "query": instruction},
                task_id=task_id, reason="查询企业数据（日历/多维表格/通讯录）",
            )
            add_trace("reporter", "data_agent", "A2A", "allowed")
            enterprise_data = await self._data_agent.query_enterprise_data(instruction, task_id)
            result["enterprise_data"] = enterprise_data
            result["steps"].append({"step": "企业数据查询", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("reporter", "data_agent", "A2A", "denied")
            result["steps"].append({"step": "企业数据查询", "status": "denied"})

        try:
            add_trace("reporter", "search_agent", "A2A", "pending")
            await self.call_agent(
                callee_agent_id=self.search_agent_id,
                message={"action": "search", "query": instruction},
                task_id=task_id, reason="搜索外部公开信息",
            )
            add_trace("reporter", "search_agent", "A2A", "allowed")
            search_data = await self._search_agent.search(instruction, task_id)
            result["external_search"] = search_data
            result["steps"].append({"step": "外部搜索", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("reporter", "search_agent", "A2A", "denied")
            result["steps"].append({"step": "外部搜索", "status": "denied"})

        if self._analyzer_agent:
            try:
                add_trace("reporter", "analyzer", "A2A", "pending")
                await self.call_agent(
                    callee_agent_id=self.analyzer_agent_id,
                    message={"action": "analyze"},
                    task_id=task_id, reason="分析多源数据并生成图表",
                )
                add_trace("reporter", "analyzer", "A2A", "allowed")
                result["analysis"] = await self._analyzer_agent.analyze(
                    task_id, enterprise_data=enterprise_data, search_data=search_data)
                result["steps"].append({"step": "数据分析", "status": "ok"})
            except PermissionDeniedError as e:
                add_trace("reporter", "analyzer", "A2A", "denied")
                result["steps"].append({"step": "数据分析", "status": "denied"})

        try:
            add_trace("reporter", "lark_doc", "MCP", "pending")
            report_content = await self._build_report(instruction, result)
            await self.call_mcp_tool(
                tool_name="lark_doc", tool_owner="reporter",
                tool_args={"action": "create", "title": f"综合分析报告: {instruction[:30]}",
                           "content": report_content},
                task_id=task_id, reason="生成综合分析报告并写入飞书文档",
            )
            add_trace("reporter", "lark_doc", "MCP", "allowed")
            result["report"] = await self._doc.execute(
                "create", title=f"综合分析报告: {instruction[:30]}", content=report_content)
            result["steps"].append({"step": "写入飞书文档", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("reporter", "lark_doc", "MCP", "denied")
            result["steps"].append({"step": "写入飞书文档", "status": "denied"})

        result["summary"] = await self._gen_summary(instruction, result)
        await self.finalize_task(task_id)
        return result

    # ================================================================
    # 辅助方法
    # ================================================================
    async def _build_report(self, instruction: str, result: dict) -> str:
        parts = []
        if result.get("enterprise_data"):
            parts.append(f"企业数据: {str(result['enterprise_data'])[:200]}")
        if result.get("external_search"):
            parts.append(f"外部数据: {str(result['external_search'])[:200]}")
        if result.get("analysis"):
            parts.append(f"分析: {str(result['analysis'])[:200]}")
        prompt = f"基于以下数据生成报告（Markdown，中文）:\n" + "\n".join(parts)
        try:
            return await chat(prompt, system="你是报告助手，输出Markdown。")
        except Exception:
            return f"# 报告\n\n" + "\n".join(parts)

    async def _gen_summary(self, instruction: str, result: dict) -> str:
        lines = []
        for t in result.get("trace", []):
            icon = "✅" if t["status"] == "allowed" else "🔴"
            lines.append(f"{icon} {t['caller']} → {t['target']} [{t['call_type']}]")
        ev = ""
        if result.get("security_events"):
            ev = "【安全事件】" + "; ".join(e["detail"] for e in result["security_events"])
        prompt = f"任务: {instruction}\n调用链:\n" + "\n".join(lines) + f"\n{ev}\n\n一段中文总结。"
        try:
            return await chat(prompt, system="你是任务总结助手。")
        except Exception:
            return f"场景 {result.get('scenario','?')} 执行完毕，共 {len(result.get('steps',[]))} 步。"
