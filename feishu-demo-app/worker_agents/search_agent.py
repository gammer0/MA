"""外部检索 Agent — 统一入口，由编排器规划具体调用哪些工具"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_sdk import SecureAgentClient


class SearchAgent(SecureAgentClient):
    """外部检索 Agent — 网页搜索 + 内容抓取"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str):
        super().__init__(agent_id, private_key_pem, gateway_url)

