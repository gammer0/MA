"""编排器 Agent"""
from agent_sdk.secure_agent_client import SecureAgentClient, PermissionDeniedError


class OrchestratorAgent(SecureAgentClient):
    """编排器 Agent — 调度 Worker Agent 完成任务"""

    async def execute_task(self, task_id: str, instruction: str, event_queue: list = None) -> dict:
        """解析指令、制定计划、调度执行、finalize 任务。"""
        result = {"task_id": task_id, "instruction": instruction, "steps": []}

        # Step 1: 调 searcher（演示正常 A2A - 场景1）
        if "搜索" in instruction:
            self._emit(event_queue, {
                "event": "step", "step": "search",
                "message": "调度搜索器搜索数据..."
            })
            try:
                search_result = await self.call_agent(
                    callee_agent_id="searcher",
                    message={"action": "search", "query": instruction},
                    task_id=task_id,
                )
                result["search"] = search_result
                result["steps"].append({"step": "search", "status": "ok"})
                self._emit(event_queue, {
                    "event": "step_done", "step": "search",
                    "message": "搜索完成"
                })
            except PermissionDeniedError as e:
                result["steps"].append({"step": "search", "status": "denied", "reason": str(e)})
                self._emit(event_queue, {
                    "event": "step_failed", "step": "search",
                    "message": f"搜索器调用被拒绝: {e}"
                })

        # Step 2: 调 analyzer（演示正常 A2A）
        if "分析" in instruction or "报告" in instruction:
            self._emit(event_queue, {
                "event": "step", "step": "analyze",
                "message": "调度分析器分析数据..."
            })
            try:
                analysis = await self.call_agent(
                    callee_agent_id="analyzer",
                    message={"action": "analyze", "data": result.get("search", {})},
                    task_id=task_id,
                )
                result["analysis"] = analysis
                result["steps"].append({"step": "analyze", "status": "ok"})
                self._emit(event_queue, {
                    "event": "step_done", "step": "analyze",
                    "message": "分析完成"
                })
            except PermissionDeniedError as e:
                result["steps"].append({"step": "analyze", "status": "denied", "reason": str(e)})
                self._emit(event_queue, {
                    "event": "step_failed", "step": "analyze",
                    "message": f"分析器调用被拒绝: {e}"
                })

        # Step 3: 写报告（演示公共 MCP 调用）
        self._emit(event_queue, {
            "event": "step", "step": "report",
            "message": "写入分析报告..."
        })
        try:
            report = await self.call_mcp_tool(
                tool_name="file_write",
                tool_owner="public",
                tool_args={"path": f"/reports/{task_id}.md", "content": str(result)},
                task_id=task_id,
            )
            result["report"] = report
            result["steps"].append({"step": "report", "status": "ok"})
            self._emit(event_queue, {
                "event": "step_done", "step": "report",
                "message": "报告写入完成"
            })
        except PermissionDeniedError as e:
            result["steps"].append({"step": "report", "status": "denied", "reason": str(e)})

        # 任务结束，级联清理
        await self.finalize_task(task_id)

        self._emit(event_queue, {
            "event": "task_completed",
            "task_id": task_id,
            "message": "任务执行完毕"
        })
        return result

    def _emit(self, queue: list | None, event: dict) -> None:
        """向事件队列发送事件。"""
        if queue is not None:
            queue.append(event)
