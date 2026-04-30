"""审计模块 - FastAPI 入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine

from config import DATABASE_URL
from handlers import router
from middleware import AdminAPIKeyMiddleware, ServiceAPIKeyMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    app.state.db_engine = create_async_engine(DATABASE_URL, echo=False)
    yield
    await app.state.db_engine.dispose()


app = FastAPI(
    title="审计模块",
    description="多Agent协作系统安全审计与调用链追溯",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(AdminAPIKeyMiddleware)
app.add_middleware(ServiceAPIKeyMiddleware)

app.include_router(router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "audit-service"}
