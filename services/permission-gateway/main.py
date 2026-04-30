"""权限网关 - FastAPI 入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine
from redis.asyncio import Redis

from config import DATABASE_URL, REDIS_URL
from handlers import router
from middleware import AdminAPIKeyMiddleware, ServiceAPIKeyMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    app.state.db_engine = create_async_engine(DATABASE_URL, echo=False)
    app.state.redis = Redis.from_url(REDIS_URL, decode_responses=True)
    yield
    await app.state.db_engine.dispose()
    await app.state.redis.close()


app = FastAPI(
    title="权限网关",
    description="Agent 权限管控与调用拦截",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(ServiceAPIKeyMiddleware)
app.add_middleware(AdminAPIKeyMiddleware)

app.include_router(router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "permission-gateway"}
