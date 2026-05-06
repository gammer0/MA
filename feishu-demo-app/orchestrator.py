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
from mcp_tools.lark_tools import LarkDocTool, LarkBaseTool, LarkContactTool, LarkCalendarTool
from mcp_tools.search_tools import WebSearchTool, PageFetchTool
from llm_client import chat


class ReporterAgent(SecureAgentClient):
    """FPGA 模式编排器 — LLM 规划，编排器逐行执行"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str,
                 data_agent=None, search_agent=None):
        super().__init__(agent_id, private_key_pem, gateway_url)
        self._data_agent = data_agent
        self._search_agent = search_agent
        self._doc = LarkDocTool()
        self._rebuild_agent_index()

    def _rebuild_agent_index(self):
        """根据当前 _data_agent / _search_agent 重建 _agents 索引"""
        self._agents = {}
        if self._data_agent:
            self._agents["data_agent"] = {
                "instance": self._data_agent,
                "agent_id": self._data_agent.agent_id,
                "desc": "企业数据 Agent，有权访问飞书日历/通讯录/多维表格",
            }
        if self._search_agent:
            self._agents["search_agent"] = {
                "instance": self._search_agent,
                "agent_id": self._search_agent.agent_id,
                "desc": "外部检索 Agent，仅可访问公开网页，无权访问飞书企业数据",
            }
        # 所有工具的实例清单（编排器直接执行 MCP）
        self._tools = {
            "lark_calendar": {"instance": LarkCalendarTool(), "desc": "查询飞书日历日程"},
            "lark_base": {"instance": LarkBaseTool(), "desc": "查询飞书多维表格"},
            "lark_contact": {"instance": LarkContactTool(), "desc": "搜索飞书通讯录"},
            "web_search": {"instance": WebSearchTool(), "desc": "公开网页搜索"},
            "page_fetch": {"instance": PageFetchTool(), "desc": "网页内容抓取"},
            "lark_doc": {"instance": self._doc, "desc": "创建飞书云文档"},
        }

    async def execute_task(self, task_id: str, instruction: str) -> dict:
        """LLM 规划 → 逐行执行 → 结果汇总"""
        result = {"task_id": task_id, "instruction": instruction,
                  "steps": [], "security_events": [], "summary": ""}

        # 重建索引（外部可能在 lifespan 中设置了 data_agent/search_agent）
        self._rebuild_agent_index()

        # 阶段 1: LLM 规划执行计划
        plan = await self._plan(instruction)

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
        """LLM 规划执行步骤（软编码：在 prompt 中定义工具链规则）"""
        prompt = (
            f"根据用户指令，从以下资源规划执行步骤。\n\n"
            f"可用 MCP 工具（编排器可直接调用）：\n"
            f"- lark_calendar (Owner: data_agent) — 查询飞书日历日程\n"
            f"- lark_base (Owner: data_agent) — 查询飞书多维表格数据\n"
            f"- lark_contact (Owner: data_agent) — 搜索飞书通讯录\n"
            f"- web_search (Owner: search_agent) — 公开网页搜索\n"
            f"- page_fetch (Owner: search_agent) — 网页内容抓取\n"
            f"- lark_doc (Owner: reporter) — 创建飞书云文档\n\n"
            f"规则：\n"
            f"1. 涉及飞书企业数据（日历/通讯录/多维表格）的查询，必须用 lark_calendar/lark_base/lark_contact\n"
            f"2. 涉及外部公开信息或网络数据的搜索，必须用 web_search/page_fetch\n"
            f"3. 需要写入文档时最后一步用 lark_doc\n"
            f"4. 尽量使用最少的步骤完成用户指令\n\n"
            f"每步格式：{{'type':'mcp','target':'工具名','reason':'为什么','params':{{工具参数}}}}\n"
            f"lark_calendar 参数: {{\"action\":\"agenda\"}}\n"
            f"lark_base 参数: {{\"action\":\"records\",\"table_id\":\"要查询的表ID\"}}\n"
            f"lark_contact 参数: {{\"action\":\"search\",\"keyword\":\"关键词\"}}\n"
            f"web_search 参数: {{\"query\":\"搜索词\"}}\n"
            f"page_fetch 参数: {{\"url\":\"要抓取的URL\"}}\n"
            f"lark_doc 参数: {{\"action\":\"create\",\"title\":\"文档标题\",\"content\":\"Markdown内容\"}}\n\n"
            f"只输出 JSON 数组，不要额外文字。\n\n"
            f"用户指令: {instruction}"
        )
        try:
            text = await chat(prompt, system="你是一个严谨的编排规划器，只输出JSON。")
            text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            return json.loads(text.strip())
        except Exception:
            return [
                {"type": "mcp", "target": "lark_calendar", "reason": "查询团队日历", "params": {"action": "agenda"}},
                {"type": "mcp", "target": "web_search", "reason": "搜索网络数据", "params": {"query": instruction}},
                {"type": "mcp", "target": "lark_doc", "reason": "创建飞书云文档", "params": {"action": "create", "title": "报告", "content": "待补充"}},
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
                entry["status"] = "allowed"
            except PermissionDeniedError as e:
                entry["status"] = "denied"
                entry["error"] = str(e)

        elif t == "mcp":
            # 工具 → Owner 映射表
            tool_owner_map = {
                "lark_calendar": "data_agent",
                "lark_base": "data_agent",
                "lark_contact": "data_agent",
                "web_search": "search_agent",
                "page_fetch": "search_agent",
                "lark_doc": "reporter",
            }
            # 工具 → 执行函数映射表
            tool_map = {
                "lark_calendar": (self._tools["lark_calendar"]["instance"], "agenda"),
                "lark_base": (self._tools["lark_base"]["instance"], "records"),
                "lark_contact": (self._tools["lark_contact"]["instance"], "search"),
                "web_search": (self._tools["web_search"]["instance"], "execute"),
                "page_fetch": (self._tools["page_fetch"]["instance"], "execute"),
                "lark_doc": (self._doc, "create"),
            }

            owner = tool_owner_map.get(target)
            tool_info = tool_map.get(target)
            if not owner or not tool_info:
                entry["status"] = "error"
                entry["error"] = f"未知工具: {target}"
                return entry

            tool_instance, default_action = tool_info
            try:
                params = step.get("params", {})
                action = params.get("action", default_action)

                # 调用网关权限校验
                await self.call_mcp_tool(
                    tool_name=target, tool_owner=owner,
                    tool_args=params, task_id=task_id, reason=step.get("reason", ""),
                )

                # 执行实际工具调用
                if target == "lark_doc":
                    entry["output"] = await tool_instance.execute(
                        action, title=params.get("title", ""), content=params.get("content", ""))
                elif target in ("web_search", "page_fetch"):
                    entry["output"] = await tool_instance.execute(params.get("query", instruction))
                elif target == "lark_calendar":
                    entry["output"] = await tool_instance.execute(action)
                elif target == "lark_base":
                    entry["output"] = await tool_instance.execute(action, table_id=params.get("table_id", "query"))
                elif target == "lark_contact":
                    entry["output"] = await tool_instance.execute(action, keyword=params.get("keyword", instruction))

                entry["status"] = "allowed"

                # 越权拦截检测
                if isinstance(entry.get("output"), dict) and "denied" in str(entry["output"]).lower() and "error" in str(entry["output"]).lower():
                    entry["security_event"] = {"event": "越权拦截", "detail": f"{target} 调用被拒绝", "result": str(entry["output"])}

            except PermissionDeniedError as e:
                entry["status"] = "denied"
                entry["error"] = str(e)
                # 如果被拒绝的原因是 explicitly_denied，标记安全事件
                if "explicitly_denied" in str(e) or "denied" in str(e):
                    entry["security_event"] = {"event": "越权拦截", "detail": f"{target} 被 deny 令牌阻止", "result": str(e)}
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
