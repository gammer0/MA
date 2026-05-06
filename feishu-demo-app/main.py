"""飞书 Demo App — FastAPI 入口"""
import os
import uuid
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pathlib import Path

from config import GATEWAY_URL
import sys
from pathlib import Path

_sdk_root = Path(__file__).parent.parent
sys.path.insert(0, str(_sdk_root))

from agent_sdk import AgentRegistry
from agent_sdk.key_store import DEFAULT_KEY_FILE, DEFAULT_SALT_FILE
from orchestrator import ReporterAgent
from worker_agents.data_agent import DataAgent
from worker_agents.search_agent import SearchAgent

# Agent 注册中心（加密本地文件持久化 + 热注入）
registry = AgentRegistry(gateway_url=GATEWAY_URL, key_file=DEFAULT_KEY_FILE, salt_file=DEFAULT_SALT_FILE)


def _init_lark_cli():
    """自动配置 lark-cli 飞书凭证（从环境变量）。"""
    import json as _json
    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        return
    try:
        config_path = os.path.expanduser("~/.config/lark-cli/config.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            _json.dump({"app_id": app_id, "app_secret": app_secret, "domain": "feishu"}, f)
        print(f"[lark-cli] 配置文件已写入: {config_path}")
    except Exception as e:
        print(f"[lark-cli] 自动配置失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_lark_cli()

    # 注册 Agent 类型（不创建实例，等密钥注入或本地文件恢复）
    registry.register("reporter", ReporterAgent, data_agent=None, search_agent=None)
    registry.register("data_agent", DataAgent)
    registry.register("search_agent", SearchAgent)

    # 注入 reporter 的依赖
    data_agent = registry.get("data_agent")
    search_agent = registry.get("search_agent")
    reporter = registry.get("reporter")
    if reporter and data_agent and search_agent:
        reporter._data_agent = data_agent
        reporter._search_agent = search_agent

    app.state.registry = registry
    yield


app = FastAPI(title="飞书 Demo App", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_active_ws: dict[str, list] = {}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "feishu-demo-app"}


@app.post("/admin/keys")
async def admin_inject_keys(request: Request):
    """POST /admin/keys — 运行时注入 Agent 凭证（热注入）。"""
    body = await request.json()
    for name in body:
        if "private_key" in body[name]:
            body[name]["private_key"] = body[name]["private_key"].replace("\\n", "\n")
    registry.inject_keys(body)
    # 注入 reporter 的依赖关联
    data_agent = registry.get("data_agent")
    search_agent = registry.get("search_agent")
    reporter = registry.get("reporter")
    if reporter and data_agent and search_agent:
        reporter._data_agent = data_agent
        reporter._search_agent = search_agent
    return {"status": "ok"}


@app.post("/tasks/execute")
async def execute_task(request: Request):
    body = await request.json()
    instruction = body.get("instruction", "")
    task_id = str(uuid.uuid4())

    reporter = app.state.registry.get("reporter")
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
async def ws_task(websocket: WebSocket, task_id: str):
    await websocket.accept()
    _active_ws.setdefault(task_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _active_ws.get(task_id, []).remove(websocket)


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
