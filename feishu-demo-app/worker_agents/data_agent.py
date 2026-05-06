"""企业数据 Agent — 统一入口，由编排器规划具体调用哪些工具"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_sdk import SecureAgentClient


class DataAgent(SecureAgentClient):
    """企业数据 Agent — 飞书通讯录/日历/多维表格"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str):
        super().__init__(agent_id, private_key_pem, gateway_url)

