"""Demo App — 多Agent协作演示系统（独立于安全内核）

凭证加载优先级：运行时热注入 > 环境变量。无硬编码默认值。
启动后需通过 POST /admin/keys 注入凭证，否则 Agent 签名将失败。
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pathlib import Path

from config import GATEWAY_URL
from web_ui import router as web_router, set_agent_registry
from orchestrator import OrchestratorAgent
from worker_agents.searcher_agent import SearcherAgent
from worker_agents.analyzer_agent import AnalyzerAgent


# ============================================================
# Agent 凭证（仅从环境变量读取，无硬编码默认值）
# 环境变量格式:
#   AGENT_ORCHESTRATOR_ID=uuid
#   AGENT_ORCHESTRATOR_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n
#   AGENT_SEARCHER_ID=uuid
#   ...
# ============================================================

def _read_agent_env(name: str):
    """读取环境变量中的 Agent 凭证。私钥中 \\n 转为换行。"""
    agent_id = os.getenv(f"AGENT_{name}_ID", "")
    pk = os.getenv(f"AGENT_{name}_PRIVATE_KEY", "")
    return {
        "agent_id": agent_id,
        "private_key": pk.replace("\\n", "\n") if pk else "",
    }

# 初始化：从环境变量加载
DEMO_KEYS = {
    "orchestrator": _read_agent_env("ORCHESTRATOR"),
    "searcher": _read_agent_env("SEARCHER"),
    "analyzer": _read_agent_env("ANALYZER"),
}

# 运行时热注入（优先级最高）
_runtime_keys: dict = {}


def inject_keys(keys: dict):
    """运行时注入 Agent 凭证。"""
    global _runtime_keys
    _runtime_keys = keys


def _get_keys():
    """获取凭证：运行时注入 > 环境变量。"""
    return _runtime_keys if _runtime_keys else DEMO_KEYS


@asynccontextmanager
async def lifespan(app: FastAPI):
    keys = _get_keys()
    searcher = SearcherAgent(
        agent_id=keys["searcher"]["agent_id"] or "searcher",
        private_key_pem=keys["searcher"]["private_key"],
        gateway_url=GATEWAY_URL,
    )
    analyzer = AnalyzerAgent(
        agent_id=keys["analyzer"]["agent_id"] or "analyzer",
        private_key_pem=keys["analyzer"]["private_key"],
        gateway_url=GATEWAY_URL,
    )
    orchestrator = OrchestratorAgent(
        agent_id=keys["orchestrator"]["agent_id"] or "orchestrator",
        private_key_pem=keys["orchestrator"]["private_key"],
        gateway_url=GATEWAY_URL,
        searcher=searcher,
        analyzer=analyzer,
    )
    app.state.agents = {
        "orchestrator": orchestrator,
        "searcher": searcher,
        "analyzer": analyzer,
    }
    set_agent_registry(app.state.agents)
    yield


app = FastAPI(
    title="Demo App - 多Agent协作演示",
    description="独立于安全内核的演示系统，通过 HTTP API 与权限网关交互",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(web_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "demo-app"}


@app.post("/admin/keys")
async def admin_inject_keys(request: Request):
    """
    POST /admin/keys — 运行时注入 Agent 凭证。
    由 batch_register.py 调用，私钥注入后立即清除全局变量（用后即焚）。
    """
    body = await request.json()
    admin_key = request.headers.get("X-Admin-API-Key", "")
    expected = os.getenv("ADMIN_API_KEY", "admin-secret-key-dev")
    if admin_key != expected:
        raise HTTPException(status_code=401, detail="Invalid admin key")

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

    inject_keys({})  # 用后即焚
    return {"status": "ok", "message": f"Keys injected for {list(body.keys())}"}
