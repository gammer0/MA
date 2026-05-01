"""执行层 - FastAPI 入口"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from config import GATEWAY_URL
from web_ui import router as web_router, set_agent_registry
from orchestrator import OrchestratorAgent
from worker_agents.searcher_agent import SearcherAgent
from worker_agents.analyzer_agent import AnalyzerAgent


# ============================================================
# Agent 初始化（优先级：运行时注入 > 环境变量 > 默认值）
# ============================================================

DEMO_KEYS = {
    "orchestrator": {
        "agent_id": os.getenv("AGENT_ORCHESTRATOR_ID", "3b3333ee-a17d-4ffb-a373-d52f91e09a5d"),
        "private_key": os.getenv("AGENT_ORCHESTRATOR_PRIVATE_KEY",
            "-----BEGIN PRIVATE KEY-----\naS/sIqoYKr09JbW1m+2XAwDgKIJRjM+6TRTwrmpbRBQ=\n-----END PRIVATE KEY-----\n"
        ).replace("\\n", "\n"),
    },
    "searcher": {
        "agent_id": os.getenv("AGENT_SEARCHER_ID", "fea00823-4bf1-4b7e-8fe1-6f69b844f54b"),
        "private_key": os.getenv("AGENT_SEARCHER_PRIVATE_KEY",
            "-----BEGIN PRIVATE KEY-----\nD/G1GDx5hoNgKXZ8gRhfSwKFu8k1ipWHDMQR+k/yqRM=\n-----END PRIVATE KEY-----\n"
        ).replace("\\n", "\n"),
    },
    "analyzer": {
        "agent_id": os.getenv("AGENT_ANALYZER_ID", "d1476ffa-0157-4685-9127-59790abba03c"),
        "private_key": os.getenv("AGENT_ANALYZER_PRIVATE_KEY",
            "-----BEGIN PRIVATE KEY-----\nc/A7SQ4OqRsV4HokDYOnR6W8yWDGIr73VqdT5H9SIAE=\n-----END PRIVATE KEY-----\n"
        ).replace("\\n", "\n"),
    },
}

# 运行时热注入（优先级最高，batch_register.py 通过 API 注入）
_runtime_keys: dict = {}


def inject_keys(keys: dict):
    """运行时注入 Agent 凭证（由 batch_register.py 通过 POST /admin/keys 调用）。"""
    global _runtime_keys
    _runtime_keys = keys


def _get_keys():
    """获取当前有效的密钥（运行时注入优先）。"""
    return _runtime_keys if _runtime_keys else DEMO_KEYS


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 — 初始化 Agent 实例"""
    keys = _get_keys()
    searcher = SearcherAgent(
        agent_id=keys["searcher"]["agent_id"],
        private_key_pem=keys["searcher"]["private_key"],
        gateway_url=GATEWAY_URL,
    )
    analyzer = AnalyzerAgent(
        agent_id=keys["analyzer"]["agent_id"],
        private_key_pem=keys["analyzer"]["private_key"],
        gateway_url=GATEWAY_URL,
    )
    orchestrator = OrchestratorAgent(
        agent_id=keys["orchestrator"]["agent_id"],
        private_key_pem=keys["orchestrator"]["private_key"],
        gateway_url=GATEWAY_URL,
        searcher_id=keys["searcher"]["agent_id"],
        analyzer_id=keys["analyzer"]["agent_id"],
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
    title="执行层",
    description="多Agent协作模板系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(web_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "execution-layer"}


@app.post("/admin/keys")
async def admin_inject_keys(request: Request):
    """
    POST /admin/keys — 运行时注入 Agent 凭证。
    由 batch_register.py 在注册完成后调用，无需中间文件传递私钥。
    """
    body = await request.json()
    admin_key = request.headers.get("X-Admin-API-Key", "")
    expected = os.getenv("ADMIN_API_KEY", "admin-secret-key-dev")
    if admin_key != expected:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    # 格式化私钥（\n → 换行）
    for name in body:
        if "private_key" in body[name]:
            body[name]["private_key"] = body[name]["private_key"].replace("\\n", "\n")

    inject_keys(body)

    # 更新已有 agent 实例的凭证
    if hasattr(app.state, "agents"):
        keys = _get_keys()
        for name, agent in app.state.agents.items():
            if name in keys:
                agent.agent_id = keys[name]["agent_id"]
                agent._private_key = keys[name]["private_key"]

    # 用后即焚：清除全局变量中的私钥，仅保留在 agent 实例中
    inject_keys({})

    return {"status": "ok", "message": f"Keys injected for {list(body.keys())}"}
