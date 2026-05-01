"""编排器 Agent"""
from agent_sdk.secure_agent_client import SecureAgentClient, PermissionDeniedError


class OrchestratorAgent(SecureAgentClient):
    """编排器 Agent — 调度 Worker Agent 完成任务"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str,
                 searcher=None, analyzer=None):
        super().__init__(agent_id, private_key_pem, gateway_url)
        self._searcher = searcher
        self._analyzer = analyzer

    @property
    def searcher_id(self):
        return self._searcher.agent_id if self._searcher else "searcher"

    @property
    def analyzer_id(self):
        return self._analyzer.agent_id if self._analyzer else "analyzer"

    async def execute_task(self, task_id: str, instruction: str) -> dict:
        """解析指令、制定计划、调度执行、finalize 任务。"""
        result = {"task_id": task_id, "instruction": instruction, "steps": [], "trace": [], "answer": ""}

        def add_trace(caller, target, call_type, status, tool_owner=""):
            result["trace"].append({
                "caller": caller, "target": target, "call_type": call_type,
                "status": status, "tool_owner": tool_owner
            })

        search_data = {}
        analysis_data = {}

        # Step 1: 搜索
        if self._searcher:
            try:
                add_trace("orchestrator", "searcher", "A2A", "pending")
                # 过网关
                gate_result = await self.call_agent(
                    callee_agent_id=self.searcher_id,
                    message={"action": "search", "query": instruction},
                    task_id=task_id,
                    reason=f"搜索 \"{instruction[:50]}\" 相关数据",
                )
                add_trace("orchestrator", "searcher", "A2A", "allowed")
                search_data = await self._searcher.search(instruction, task_id)
                result["search"] = search_data
                result["steps"].append({"step": "search", "status": "ok"})
            except PermissionDeniedError as e:
                add_trace("orchestrator", "searcher", "A2A", "denied")
                result["steps"].append({"step": "search", "status": "denied", "reason": str(e)})

        # Step 2: 分析
        if self._analyzer:
            try:
                add_trace("orchestrator", "analyzer", "A2A", "pending")
                gate_result = await self.call_agent(
                    callee_agent_id=self.analyzer_id,
                    message={"action": "analyze", "data": search_data},
                    task_id=task_id,
                    reason="分析搜索结果并生成报告",
                )
                add_trace("orchestrator", "analyzer", "A2A", "allowed")
                analysis_data = await self._analyzer.analyze(search_data, task_id)
                result["analysis"] = analysis_data
                result["steps"].append({"step": "analyze", "status": "ok"})
                if isinstance(analysis_data, dict) and isinstance(analysis_data.get("chart"), str):
                    if "denied" in analysis_data["chart"].lower():
                        add_trace("analyzer", "chart_gen(自有)", "MCP", "denied")
            except PermissionDeniedError as e:
                add_trace("orchestrator", "analyzer", "A2A", "denied")
                result["steps"].append({"step": "analyze", "status": "denied", "reason": str(e)})

        # Step 3: 写报告
        try:
            add_trace("orchestrator", "file_write", "MCP(公共)", "pending")
            report_content = self._build_answer(instruction, search_data, analysis_data)
            report = await self.call_mcp_tool(
                tool_name="file_write",
                tool_owner="public",
                tool_args={"path": f"/reports/{task_id}.md", "content": report_content},
                task_id=task_id,
                reason="将分析报告写入文件",
            )
            add_trace("orchestrator", "file_write", "MCP(公共)", "allowed")
            result["report"] = report
            result["answer"] = report_content
            result["steps"].append({"step": "report", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("orchestrator", "file_write", "MCP(公共)", "denied")
            result["steps"].append({"step": "report", "status": "denied", "reason": str(e)})

        await self.finalize_task(task_id)
        return result

    def _build_answer(self, instruction: str, search: dict, analysis: dict) -> str:
        """根据搜索和分析结果生成回答。"""
        parts = [f"📋 **任务指令**: {instruction}\n"]
        parts.append("---\n")

        # 搜索结果
        if search.get("search"):
            parts.append("## 🔍 搜索结果\n")
            sr = search.get("search", {})
            results = sr.get("results", [])
            for r in results:
                parts.append(f"- {r}")
            if search.get("page", {}).get("content"):
                parts.append(f"\n详细内容: {search['page']['content'][:300]}...")
            parts.append("")

        # 分析结果
        if analysis:
            parts.append("## 📊 分析结果\n")
            calc = analysis.get("analysis", "")
            if isinstance(analysis, dict):
                calc = analysis.get("analysis", str(analysis)[:200])
            parts.append(f"计算结果: {calc}")

            # 图表
            chart = analysis.get("chart", "")
            if chart and "denied" not in str(chart).lower():
                parts.append(f"图表: {chart}")
            elif chart:
                parts.append(f"⚠️ 图表生成被安全策略阻止: {chart}")

            # 补充搜索
            supp = analysis.get("supplement", "")
            if supp and "denied" not in str(supp).lower():
                parts.append(f"补充信息: {str(supp)[:200]}")
            parts.append("")

        parts.append(f"---\n✅ 任务执行完毕")
        return "\n".join(parts)
