"""权限网关 - 配置模块"""
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://agent:changeme@localhost:5432/agent_security"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/1")
IDENTITY_SERVICE_URL = os.getenv("IDENTITY_SERVICE_URL", "http://localhost:8001")
AUDIT_SERVICE_URL = os.getenv("AUDIT_SERVICE_URL", "http://localhost:8003")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "service-secret-key-dev")

# 临时权限 TTL 上限（秒）
MAX_TEMP_PERMISSION_TTL = int(os.getenv("MAX_TEMP_PERMISSION_TTL", "3600"))

# 令牌视图 Redis 缓存 TTL（秒）
VIEW_CACHE_TTL = int(os.getenv("VIEW_CACHE_TTL", "300"))
