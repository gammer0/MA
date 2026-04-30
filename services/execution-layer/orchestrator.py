"""编排器 Agent"""
from agent_sdk.secure_agent_client import SecureAgentClient, PermissionDeniedError


class OrchestratorAgent(SecureAgentClient):
    """编排器 Agent — 调度 Worker Agent 完成任务"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str,
                 searcher_id: str = "searcher", analyzer_id: str = "analyzer",
                 searcher=None, analyzer=None):
        super().__init__(agent_id, private_key_pem, gateway_url)
        self.searcher_id = searcher_id
        self.analyzer_id = analyzer_id
        self._searcher = searcher
        self._analyzer = analyzer

    async def execute_task(self, task_id: str, instruction: str) -> dict:
        """解析指令、制定计划、调度执行、finalize 任务。"""
        result = {"task_id": task_id, "instruction": instruction, "steps": [], "trace": []}

        def add_trace(caller, target, call_type, status, tool_owner=""):
            result["trace"].append({
                "caller": caller, "target": target, "call_type": call_type,
                "status": status, "tool_owner": tool_owner
            })

        # Step 1: 调 searcher（演示正常 A2A - 场景1）
        if "搜索" in instruction:
            try:
                add_trace("orchestrator", "searcher", "A2A", "pending")
                gate_result = await self.call_agent(
                    callee_agent_id=self.searcher_id,
                    message={"action": "search", "query": instruction},
                    task_id=task_id,
                )
                add_trace("orchestrator", "searcher", "A2A", "allowed")
                if self._searcher:
                    search_result = await self._searcher.search(instruction, task_id)
                else:
                    search_result = {"status": "no_searcher_ref"}
                result["search"] = search_result
                result["steps"].append({"step": "search", "status": "ok"})
            except PermissionDeniedError as e:
                add_trace("orchestrator", "searcher", "A2A", "denied")
                result["steps"].append({"step": "search", "status": "denied", "reason": str(e)})

        # Step 2: 调 analyzer（演示正常 A2A + deny场景4）
        if "分析" in instruction or "报告" in instruction:
            try:
                add_trace("orchestrator", "analyzer", "A2A", "pending")
                # 先过网关权限判定
                gate_result = await self.call_agent(
                    callee_agent_id=self.analyzer_id,
                    message={"action": "analyze", "data": result.get("search", {})},
                    task_id=task_id,
                )
                add_trace("orchestrator", "analyzer", "A2A", "allowed")
                # 网关通过后，在进程中实际调用 analyzer
                if self._analyzer:
                    analysis = await self._analyzer.analyze(result.get("search", {}), task_id)
                else:
                    analysis = {"status": "no_analyzer_ref"}
                result["analysis"] = analysis
                result["steps"].append({"step": "analyze", "status": "ok"})
                # 检查 chart_gen 是否被 deny
                if isinstance(analysis, dict) and isinstance(analysis.get("chart"), str):
                    if "denied" in analysis["chart"].lower():
                        add_trace("analyzer", "chart_gen(自有)", "MCP", "denied")
            except PermissionDeniedError as e:
                add_trace("orchestrator", "analyzer", "A2A", "denied")
                result["steps"].append({"step": "analyze", "status": "denied", "reason": str(e)})

        # Step 3: 写报告（演示公共 MCP 调用）
        try:
            add_trace("orchestrator", "file_write", "MCP(公共)", "pending")
            report = await self.call_mcp_tool(
                tool_name="file_write",
                tool_owner="public",
                tool_args={"path": f"/reports/{task_id}.md", "content": str(result)},
                task_id=task_id,
            )
            add_trace("orchestrator", "file_write", "MCP(公共)", "allowed")
            result["report"] = report
            result["steps"].append({"step": "report", "status": "ok"})
        except PermissionDeniedError as e:
            add_trace("orchestrator", "file_write", "MCP(公共)", "denied")
            result["steps"].append({"step": "report", "status": "denied", "reason": str(e)})

        # 任务结束，级联清理
        await self.finalize_task(task_id)

        return result
