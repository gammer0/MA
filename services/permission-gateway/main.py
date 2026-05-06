"""权限网关 - FastAPI 入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from redis.asyncio import Redis
from pathlib import Path

from config import DATABASE_URL, REDIS_URL
from handlers import router
from middleware import ServiceAPIKeyMiddleware


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ServiceAPIKeyMiddleware)

app.include_router(router)

# 挂载静态文件
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/admin")
async def admin_page():
    """权限订阅管理 Web UI"""
    admin_html = Path(__file__).parent / "static" / "admin.html"
    if admin_html.exists():
        return HTMLResponse(admin_html.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Admin page not found</h1>", status_code=404)


@app.get("/health")
async def health_check(request: Request):
    """健康检查 — 包含数据库和 Redis 连接检测"""
    checks = {"status": "ok", "service": "permission-gateway", "checks": {}}
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
