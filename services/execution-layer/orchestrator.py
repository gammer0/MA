"""编排器 Agent"""
from agent_sdk.secure_agent_client import SecureAgentClient, PermissionDeniedError


class OrchestratorAgent(SecureAgentClient):
    """编排器 Agent — 调度 Worker Agent 完成任务"""

    async def execute_task(self, task_id: str, instruction: str) -> dict:
        """解析指令、制定计划、调度执行、finalize 任务。"""
        result = {"task_id": task_id, "instruction": instruction, "steps": []}

        # Step 1: 调 searcher（演示正常 A2A - 场景1）
        if "搜索" in instruction:
            try:
                search_result = await self.call_agent(
                    callee_agent_id="searcher",
                    message={"action": "search", "query": instruction},
                    task_id=task_id,
                )
                result["search"] = search_result
                result["steps"].append({"step": "search", "status": "ok"})
            except PermissionDeniedError as e:
                result["steps"].append({"step": "search", "status": "denied", "reason": str(e)})

        # Step 2: 调 analyzer（演示正常 A2A）
        if "分析" in instruction or "报告" in instruction:
            try:
                analysis = await self.call_agent(
                    callee_agent_id="analyzer",
                    message={"action": "analyze", "data": result.get("search", {})},
                    task_id=task_id,
                )
                result["analysis"] = analysis
                result["steps"].append({"step": "analyze", "status": "ok"})
            except PermissionDeniedError as e:
                result["steps"].append({"step": "analyze", "status": "denied", "reason": str(e)})

        # Step 3: 写报告（演示公共 MCP 调用）
        try:
            report = await self.call_mcp_tool(
                tool_name="file_write",
                tool_owner="public",
                tool_args={"path": f"/reports/{task_id}.md", "content": str(result)},
                task_id=task_id,
            )
            result["report"] = report
            result["steps"].append({"step": "report", "status": "ok"})
        except PermissionDeniedError as e:
            result["steps"].append({"step": "report", "status": "denied", "reason": str(e)})

        # 任务结束，级联清理
        await self.finalize_task(task_id)

        return result
        return result
