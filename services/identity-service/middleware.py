"""身份注册服务 - 认证中间件"""
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from config import ADMIN_API_KEY, SERVICE_API_KEY


class AdminAPIKeyMiddleware(BaseHTTPMiddleware):
    """管理接口的 API Key 认证中间件。
    适用于: /agents/*, /tools/* 的管理操作
    """

    async def dispatch(self, request: Request, call_next):
        # 跳过非管理路径
        admin_prefixes = ("/agents", "/tools")
        if not any(request.url.path.startswith(p) for p in admin_prefixes):
            return await call_next(request)

        # 跳过 GET 请求（查询接口不强制认证，可配置）
        # 如需严格认证，取消下面注释：
        # pass

        # 仅 POST/DELETE 需要管理 API Key
        if request.method in ("POST", "DELETE", "PUT", "PATCH"):
            api_key = request.headers.get("X-Admin-API-Key", "")
            if api_key != ADMIN_API_KEY:
                raise HTTPException(status_code=401, detail="Invalid admin API key")

        return await call_next(request)


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
