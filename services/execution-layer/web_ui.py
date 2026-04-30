"""执行层 - Web UI 路由"""
import uuid
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pathlib import Path

from config import GATEWAY_URL

router = APIRouter()

# 存储活跃的 WebSocket 连接
_active_connections: dict[str, list[WebSocket]] = {}

# 存储 Agent 实例（由 main.py 注入）
_agent_registry: dict = {}


def set_agent_registry(registry: dict):
    global _agent_registry
    _agent_registry = registry


async def _push_event(task_id: str, event: dict):
    """向任务的所有 WebSocket 连接推送事件。"""
    if task_id not in _active_connections:
        return
    dead = []
    for ws in _active_connections[task_id]:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _active_connections[task_id].remove(ws)


@router.get("/", response_class=HTMLResponse)
async def index():
    """Web UI 页面"""
    static_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(static_path.read_text(encoding="utf-8"))


@router.post("/tasks/execute")
async def handle_execute_task(request: dict):
    """POST /tasks/execute — 提交自然语言任务指令"""
    instruction = request.get("instruction", "")
    task_id = str(uuid.uuid4())

    orchestrator = _agent_registry.get("orchestrator")
    if orchestrator is None:
        return {"error": "Orchestrator not initialized"}

    async def run_task():
        try:
            await _push_event(task_id, {"event": "task_started", "message": "任务开始执行"})
            result = await orchestrator.execute_task(task_id, instruction)
            # 推送调用链
            if result.get("trace"):
                for step in result["trace"]:
                    await _push_event(task_id, {
                        "event": "trace_update",
                        "caller": step["caller"],
                        "target": step["target"],
                        "call_type": step["call_type"],
                        "status": step["status"],
                    })
            # 检查 analyzer 内部是否有 deny 事件
            has_deny = False
            if result.get("analysis"):
                analysis = result["analysis"]
                if isinstance(analysis, dict):
                    chart = analysis.get("chart", "")
                    supplement = analysis.get("supplement", "")
                    if isinstance(chart, str) and "denied" in chart.lower():
                        has_deny = True
                        await _push_event(task_id, {
                            "event": "task_completed", "task_id": task_id,
                            "result": {
                                "security_event": "🔴 analyzer的chart_gen被deny令牌阻止 (场景4: deny硬拒绝)",
                                "chart_result": chart,
                                "supplement": supplement if supplement else "无"
                            }
                        })

            if not has_deny:
                await _push_event(task_id, {"event": "task_completed", "task_id": task_id})

            # 推送任务结果摘要
            import json as _json
            summary = {
                "steps": result.get("steps", []),
                "search_done": "search" in result,
                "analysis_done": "analysis" in result,
                "report_done": "report" in result,
                "analysis_detail": str(result.get("analysis", ""))[:500]
            }
            await _push_event(task_id, {
                "event": "task_result",
                "result": _json.dumps(summary, indent=2, ensure_ascii=False)
            })

            # 从审计模块拉取审计日志
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as c:
                    resp = await c.get(
                        f"http://audit-service:8003/audit/tasks/{task_id}/sessions",
                        headers={"X-Admin-API-Key": "admin-secret-key-dev"}
                    )
                    if resp.status_code == 200:
                        audit_data = resp.json()
                        await _push_event(task_id, {
                            "event": "audit_log",
                            "sessions": audit_data.get("sessions", [])
                        })
            except Exception:
                pass
        except Exception as e:
            await _push_event(task_id, {"event": "task_failed", "message": str(e)})

    asyncio.create_task(run_task())

    return {"task_id": task_id, "message": "Task started."}


@router.get("/tasks/{task_id}/status")
async def handle_get_task_status(task_id: str):
    """GET /tasks/{task_id}/status"""
    return {"task_id": task_id, "status": "running"}


@router.websocket("/ws/tasks/{task_id}")
async def websocket_task_events(websocket: WebSocket, task_id: str):
    """WS /ws/tasks/{task_id} — 实时推送执行状态"""
    await websocket.accept()

    if task_id not in _active_connections:
        _active_connections[task_id] = []
    _active_connections[task_id].append(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if task_id in _active_connections:
            _active_connections[task_id].remove(websocket)
