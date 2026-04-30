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

    # 异步执行任务
    event_queue = []

    async def run_task():
        try:
            result = await orchestrator.execute_task(task_id, instruction, event_queue)
        except Exception as e:
            event_queue.append({"event": "task_failed", "message": str(e)})

    asyncio.create_task(run_task())

    return {"task_id": task_id, "message": "Task started."}


@router.get("/tasks/{task_id}/status")
async def handle_get_task_status(task_id: str):
    """GET /tasks/{task_id}/status"""
    return {"task_id": task_id, "status": "running"}


@router.get("/tasks/{task_id}/result")
async def handle_get_task_result(task_id: str):
    """GET /tasks/{task_id}/result"""
    return {"task_id": task_id, "result": "Task completed."}


@router.websocket("/ws/tasks/{task_id}")
async def websocket_task_events(websocket: WebSocket, task_id: str):
    """WS /ws/tasks/{task_id} — 实时推送执行状态"""
    await websocket.accept()

    if task_id not in _active_connections:
        _active_connections[task_id] = []
    _active_connections[task_id].append(websocket)

    try:
        while True:
            # 保持连接，等待事件
            await websocket.receive_text()
    except WebSocketDisconnect:
        _active_connections[task_id].remove(websocket)
