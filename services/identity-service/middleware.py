"""身份注册服务 - 认证中间件"""
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from config import SERVICE_API_KEY


class ServiceAPIKeyMiddleware(BaseHTTPMiddleware):
    """服务间调用的 API Key 认证中间件。
    适用于: /verify/* 等服务间接口
    """

    async def dispatch(self, request: Request, call_next):
        # 仅对 /verify 路径做服务间认证
        if request.url.path.startswith("/verify"):
            api_key = request.headers.get("X-Service-API-Key", "")
            if api_key != SERVICE_API_KEY:
                raise HTTPException(status_code=401, detail="Invalid service API key")

        return await call_next(request)
