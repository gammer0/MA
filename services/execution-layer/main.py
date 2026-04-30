"""执行层 - FastAPI 入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from config import GATEWAY_URL
from web_ui import router as web_router, set_agent_registry
from orchestrator import OrchestratorAgent
from worker_agents.searcher_agent import SearcherAgent
from worker_agents.analyzer_agent import AnalyzerAgent


# ============================================================
# Agent 初始化（演示用硬编码凭证）
# 生产环境中应从身份注册服务获取
# ============================================================

# 演示用密钥（实际应从身份注册服务注册获取）
DEMO_KEYS = {
    "orchestrator": {
        "agent_id": "orchestrator",
        "private_key": "MC4CAQAwBQYDK2VwBCIEINTv8qL5TbVfZQmP2xHNkHnJ7WrXsLqM3yVwBhRtF9Gk",
    },
    "searcher": {
        "agent_id": "searcher",
        "private_key": "MC4CAQAwBQYDK2VwBCIEIO2LpX8mYrRtVeUqNwFoPiEbMsCpPlHkSjzA0cDwDqNM",
    },
    "analyzer": {
        "agent_id": "analyzer",
        "private_key": "MC4CAQAwBQYDK2VwBCIEIExV5nJ2yKqRfTpWgHo3sCDLmA7qFtBvS9zNuMxEGpLM",
    },
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 — 初始化 Agent 实例"""
    app.state.agents = {
        "orchestrator": OrchestratorAgent(
            agent_id=DEMO_KEYS["orchestrator"]["agent_id"],
            private_key_pem=DEMO_KEYS["orchestrator"]["private_key"],
            gateway_url=GATEWAY_URL,
        ),
        "searcher": SearcherAgent(
            agent_id=DEMO_KEYS["searcher"]["agent_id"],
            private_key_pem=DEMO_KEYS["searcher"]["private_key"],
            gateway_url=GATEWAY_URL,
        ),
        "analyzer": AnalyzerAgent(
            agent_id=DEMO_KEYS["analyzer"]["agent_id"],
            private_key_pem=DEMO_KEYS["analyzer"]["private_key"],
            gateway_url=GATEWAY_URL,
        ),
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
