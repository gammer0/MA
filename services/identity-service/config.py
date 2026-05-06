"""身份注册服务 - 配置模块"""
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://agent:changeme@localhost:5432/agent_security"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "service-secret-key-dev")

# 证书默认有效期（天）
DEFAULT_CERT_TTL_DAYS = 90

# 执行层（demoapp）地址 — 注册后自动推送私钥
EXECUTION_LAYER_URL = os.getenv("EXECUTION_LAYER_URL", "http://host.docker.internal:8005")
