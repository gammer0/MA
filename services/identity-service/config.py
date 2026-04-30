"""身份注册服务 - 配置模块"""
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://agent:changeme@localhost:5432/agent_security"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin-secret-key-dev")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "service-secret-key-dev")

# 证书默认有效期（天）
DEFAULT_CERT_TTL_DAYS = 90
