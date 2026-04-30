"""身份注册服务 - FastAPI 入口"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine
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
app.add_middleware(ServiceAPIKeyMiddleware)
app.add_middleware(AdminAPIKeyMiddleware)

# 注册路由
app.include_router(router)


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "identity-service"}
