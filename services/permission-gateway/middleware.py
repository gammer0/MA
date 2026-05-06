"""权限网关 - 认证中间件"""
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from config import SERVICE_API_KEY


class ServiceAPIKeyMiddleware(BaseHTTPMiddleware):
    """服务间调用的 API Key 认证中间件。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/sessions"):
            api_key = request.headers.get("X-Service-API-Key", "")
            if api_key != SERVICE_API_KEY:
                raise HTTPException(status_code=401, detail="Invalid service API key")

        return await call_next(request)
