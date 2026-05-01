"""权限网关 - 认证中间件"""
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from config import ADMIN_API_KEY, SERVICE_API_KEY


class AdminAPIKeyMiddleware(BaseHTTPMiddleware):
    """管理接口的 API Key 认证中间件。"""

    async def dispatch(self, request: Request, call_next):
        # 仅 /tokens, /tasks 路径的写操作需要管理 API Key
        admin_prefixes = ("/tokens", "/tasks")
        if not any(request.url.path.startswith(p) for p in admin_prefixes):
            return await call_next(request)

        # 跳过 GET 请求
        if request.method == "GET":
            return await call_next(request)

        # 跳过 Agent 发起的权限申请（使用 Agent 签名认证）
        if request.url.path.endswith("/permission-requests") and request.method == "POST":
            return await call_next(request)

        # 跳过执行层存储任务指令（内部调用）
        if request.url.path.endswith("/instruction") and request.method == "POST":
            return await call_next(request)

        # 跳过 Agent 发起的任务结束（编排器通过 Agent 签名调用）
        if request.url.path.endswith("/finalize") and request.method == "POST":
            return await call_next(request)

        api_key = request.headers.get("X-Admin-API-Key", "")
        if api_key != ADMIN_API_KEY:
            raise HTTPException(status_code=401, detail="Invalid admin API key")

        return await call_next(request)


class ServiceAPIKeyMiddleware(BaseHTTPMiddleware):
    """服务间调用的 API Key 认证中间件。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/sessions"):
            api_key = request.headers.get("X-Service-API-Key", "")
            if api_key != SERVICE_API_KEY:
                raise HTTPException(status_code=401, detail="Invalid service API key")

        return await call_next(request)
