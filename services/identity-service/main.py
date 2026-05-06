"""身份注册服务 - FastAPI 入口"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from redis.asyncio import Redis

from config import DATABASE_URL, REDIS_URL
from handlers import router
from middleware import AdminAPIKeyMiddleware, ServiceAPIKeyMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时创建连接，关闭时释放。"""
    # 启动
    app.state.db_engine = create_async_engine(DATABASE_URL, echo=False)
    app.state.redis = Redis.from_url(REDIS_URL, decode_responses=True)
    yield
    # 关闭
    await app.state.db_engine.dispose()
    await app.state.redis.close()


app = FastAPI(
    title="身份注册服务",
    description="Agent 身份数字证书管理与 MCP 工具注册",
    version="0.1.0",
    lifespan=lifespan,
)

# 注册中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ServiceAPIKeyMiddleware)
app.add_middleware(AdminAPIKeyMiddleware)

# 注册路由
app.include_router(router)


@app.get("/health")
async def health_check(request: Request):
    """健康检查 — 包含数据库和 Redis 连接检测"""
    checks = {"status": "ok", "service": "identity-service", "checks": {}}
    try:
        async with request.app.state.db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["checks"]["database"] = "ok"
    except Exception as e:
        checks["status"] = "degraded"
        checks["checks"]["database"] = f"error: {e}"

    try:
        await request.app.state.redis.ping()
        checks["checks"]["redis"] = "ok"
    except Exception as e:
        checks["status"] = "degraded"
        checks["checks"]["redis"] = f"error: {e}"

    status_code = 200 if checks["status"] == "ok" else 503
    return JSONResponse(content=checks, status_code=status_code)
