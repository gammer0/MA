"""审计模块 - 配置模块"""
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://agent:changeme@localhost:5432/agent_security"
)
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "service-secret-key-dev")
