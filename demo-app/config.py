"""执行层 - 配置模块"""
import os

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8002")
