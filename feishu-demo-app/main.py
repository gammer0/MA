"""飞书 Demo App — FastAPI 入口"""
import os
import uuid
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from config import GATEWAY_URL
from orchestrator import ReporterAgent
from worker_agents.data_agent import DataAgent
from worker_agents.search_agent import SearchAgent

# Agent 凭证（默认值，启动后通过 /admin/keys 注入）
DEMO_KEYS = {
    "reporter": {"agent_id": "", "private_key": ""},
    "data_agent": {"agent_id": "", "private_key": ""},
    "search_agent": {"agent_id": "", "private_key": ""},
}

_runtime_keys: dict = {}


def inject_keys(keys: dict):
    global _runtime_keys
    _runtime_keys = keys


def _get_keys():
    return _runtime_keys if _runtime_keys else DEMO_KEYS


@asynccontextmanager
async def lifespan(app: FastAPI):
    keys = _get_keys()
    data_agent = DataAgent(
        agent_id=keys["data_agent"]["agent_id"] or "data_agent",
        private_key_pem=keys["data_agent"]["private_key"],
        gateway_url=GATEWAY_URL,
    )
    search_agent = SearchAgent(
        agent_id=keys["search_agent"]["agent_id"] or "search_agent",
        private_key_pem=keys["search_agent"]["private_key"],
        gateway_url=GATEWAY_URL,
    )
    reporter = ReporterAgent(
        agent_id=keys["reporter"]["agent_id"] or "reporter",
        private_key_pem=keys["reporter"]["private_key"],
        gateway_url=GATEWAY_URL,
        data_agent=data_agent,
        search_agent=search_agent,
    )
    app.state.agents = {"reporter": reporter, "data_agent": data_agent, "search_agent": search_agent}
    yield


app = FastAPI(title="飞书 Demo App", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# WebSocket 连接
_active_ws: dict[str, list] = {}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "feishu-demo-app"}


@app.post("/admin/keys")
async def admin_inject_keys(request: Request):
    body = await request.json()
    admin_key = request.headers.get("X-Admin-API-Key", "")
    if admin_key != os.getenv("ADMIN_API_KEY", "admin-secret-key-dev"):
        raise HTTPException(status_code=401)
    for name in body:
        if "private_key" in body[name]:
            body[name]["private_key"] = body[name]["private_key"].replace("\\n", "\n")
    inject_keys(body)
    if hasattr(app.state, "agents"):
        keys = _get_keys()
        for name, agent in app.state.agents.items():
            if name in keys:
                agent.agent_id = keys[name]["agent_id"]
                agent._private_key = keys[name]["private_key"]
    inject_keys({})
    return {"status": "ok"}


@app.post("/tasks/execute")
async def execute_task(request: Request):
    body = await request.json()
    instruction = body.get("instruction", "")
    task_id = str(uuid.uuid4())

    reporter = app.state.agents.get("reporter")
    if not reporter:
        return {"error": "Reporter not initialized"}

    # 存储任务指令到网关
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{GATEWAY_URL}/tasks/{task_id}/instruction",
                         json={"instruction": instruction})
    except Exception:
        pass

    async def run_task():
        try:
            result = await reporter.execute_task(task_id, instruction)
            for ws in _active_ws.get(task_id, []):
                try:
                    await ws.send_json({"event": "task_completed", "task_id": task_id, "result": result})
                except Exception:
                    pass
        except Exception as e:
            for ws in _active_ws.get(task_id, []):
                try:
                    await ws.send_json({"event": "task_failed", "message": str(e)})
                except Exception:
                    pass

    asyncio.create_task(run_task())
    return {"task_id": task_id, "status": "started"}


@app.websocket("/ws/tasks/{task_id}")
async def ws_task(ws, task_id: str):
    await ws.accept()
    _active_ws.setdefault(task_id, []).append(ws)
    try:
        while True:
            await ws.receive_text()
    except Exception:
        _active_ws.get(task_id, []).remove(ws)


from fastapi.responses import HTMLResponse
from pathlib import Path


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))
