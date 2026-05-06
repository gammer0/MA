"""飞书文档助手 (Reporter) — FPGA 模式编排器

编排器不硬编码调用链。每次任务由 LLM 根据指令动态规划执行步骤，
编排器按计划逐一执行：A2A 调 Agent 或 MCP 调 Tool。
所有 Agent 和 Tool 在运行前确定，本编排器直接引用固定实例。
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_sdk import SecureAgentClient, PermissionDeniedError
from mcp_tools.lark_tools import LarkDocTool
from llm_client import chat


class ReporterAgent(SecureAgentClient):
    """FPGA 模式编排器 — LLM 规划，编排器逐行执行"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str,
                 data_agent=None, search_agent=None):
        super().__init__(agent_id, private_key_pem, gateway_url)
        self._data_agent = data_agent
        self._search_agent = search_agent
        self._doc = LarkDocTool()

        # 运行前确定的 Agent 和 Tool 清单
        self._agents = {}
        if data_agent:
            self._agents["data_agent"] = {
                "instance": data_agent,
                "agent_id": data_agent.agent_id,
                "desc": "企业数据 Agent，有权访问飞书日历/通讯录/多维表格",
                "methods": ["query_enterprise_data"],
            }
        if search_agent:
            self._agents["search_agent"] = {
                "instance": search_agent,
                "agent_id": search_agent.agent_id,
                "desc": "外部检索 Agent，仅可访问公开网页，无权访问飞书企业数据",
                "methods": ["search"],
            }

        self._tools = {
            "lark_doc": {
                "instance": self._doc,
                "desc": "创建飞书云文档，参数: title(标题), content(Markdown内容)",
            },
        }

    async def execute_task(self, task_id: str, instruction: str) -> dict:
        """LLM 规划 → 逐行执行 → 结果汇总"""
        result = {"task_id": task_id, "instruction": instruction,
                  "steps": [], "security_events": [], "summary": ""}

        # 阶段 1: LLM 规划执行计划
        plan = await self._plan(instruction)
        result["plan"] = plan

        # 阶段 2: 逐行执行
        for step in plan:
            step_result = await self._execute_step(step, task_id)
            result["steps"].append(step_result)
            if step_result.get("security_event"):
                result["security_events"].append(step_result["security_event"])

        # 阶段 3: LLM 总结
        result["summary"] = await self._summary(instruction, result["steps"])

        await self.finalize_task(task_id)
        return result

    def _agent_descriptions(self) -> str:
        lines = []
        for name, info in self._agents.items():
            lines.append(f"- {name}({info['desc']})")
        return "\n".join(lines)

    def _tool_descriptions(self) -> str:
        lines = []
        for name, info in self._tools.items():
            lines.append(f"- {name}({info['desc']})")
        return "\n".join(lines)

    async def _plan(self, instruction: str) -> list:
        """LLM 规划执行步骤"""
        prompt = (
            f"根据用户指令，从以下资源规划执行步骤。\n\n"
            f"可用 Agent:\n{self._agent_descriptions()}\n\n"
            f"可用工具:\n{self._tool_descriptions()}\n\n"
            f"每步格式：{{'type':'a2a'|'mcp','target':'Agent名'|'工具名','reason':'用一句话说明为什么要做这步','params':{{}}}}\n"
            f"a2a 时 params 传给 Agent 的 message；mcp 时 params 传工具参数。\n"
            f"reason 要具体描述目的，例如'查询团队日历了解本周安排'而非'查询数据'。\n"
            f"只输出 JSON 数组，不要额外文字。\n\n"
            f"用户指令: {instruction}"
        )
        try:
            text = await chat(prompt, system="你是一个严谨的编排规划器，只输出JSON。")
            text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            return json.loads(text.strip())
        except Exception:
            return [
                {"type": "a2a", "target": "data_agent", "reason": "查询企业数据", "params": {"query": instruction}},
                {"type": "a2a", "target": "search_agent", "reason": "搜索外部信息", "params": {"query": instruction}},
                {"type": "mcp", "target": "lark_doc", "reason": "写入飞书文档", "params": {"action": "create", "title": f"报告: {instruction[:20]}"}},
            ]

    async def _execute_step(self, step: dict, task_id: str) -> dict:
        t, target = step.get("type"), step.get("target")
        entry = {"type": t, "target": target, "reason": step.get("reason", ""), "status": "pending"}

        if t == "a2a":
            info = self._agents.get(target)
            if not info:
                return {**entry, "status": "error", "error": f"未知 Agent: {target}"}
            try:
                await self.call_agent(callee_agent_id=info["agent_id"],
                                      message=step.get("params", {}), task_id=task_id,
                                      reason=step.get("reason", ""))
                output = await info["instance"].query_enterprise_data(
                    step["params"].get("query", ""), task_id
                ) if target == "data_agent" else await info["instance"].search(
                    step["params"].get("query", ""), task_id)
                entry["status"] = "allowed"
                if isinstance(output, dict) and output.get("lark_base_hijack"):
                    entry["security_event"] = {"event": "越权拦截",
                        "detail": f"{target} 调用 lark_base 被 deny 阻止", "result": output["lark_base_hijack"]}
            except PermissionDeniedError as e:
                entry["status"] = "denied"
                entry["error"] = str(e)

        elif t == "mcp":
            if target == "lark_doc":
                try:
                    await self.call_mcp_tool(tool_name="lark_doc", tool_owner="reporter",
                                             tool_args=step.get("params", {}), task_id=task_id,
                                             reason=step.get("reason", ""))
                    p = step.get("params", {})
                    entry["output"] = await self._doc.execute(
                        p.get("action", "create"), title=p.get("title", ""), content=p.get("content", ""))
                    entry["status"] = "allowed"
                except PermissionDeniedError as e:
                    entry["status"] = "denied"
                    entry["error"] = str(e)
            else:
                entry["status"] = "error"
                entry["error"] = f"未知工具: {target}"
        else:
            entry["status"] = "error"
            entry["error"] = f"未知类型: {t}"

        return entry

    async def _summary(self, instruction: str, steps: list) -> str:
        lines = [(f"✅ {s['target']}" if s["status"] == "allowed" else f"🔴 {s['target']}") +
                 f" [{s['status']}] {s.get('reason','')}" for s in steps]
        prompt = f"任务: {instruction}\n步骤:\n" + "\n".join(lines) + "\n\n用一段中文总结。"
        try:
            return await chat(prompt, system="你是任务总结助手。")
        except Exception:
            return f"任务「{instruction[:30]}...」执行完毕。"
