"""权限网关 - 身份注册服务 HTTP 客户端"""
import httpx
from config import IDENTITY_SERVICE_URL, SERVICE_API_KEY


async def verify_signature(
    agent_id: str,
    session_id: str,
    call_id: str,
    timestamp: str,
    request_body: str,
    signature_hex: str,
    callee_agent_id: str = "",
    mcp_tool_name: str = "",
    tool_owner: str = "",
) -> bool:
    """调身份注册服务验签。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{IDENTITY_SERVICE_URL}/verify/signature",
                json={
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "call_id": call_id,
                    "timestamp": timestamp,
                    "request_body": request_body,
                    "signature_hex": signature_hex,
                    "callee_agent_id": callee_agent_id,
                    "mcp_tool_name": mcp_tool_name,
                    "tool_owner": tool_owner,
                },
                headers={"X-Service-API-Key": SERVICE_API_KEY},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("verified", False)
            return False
        except httpx.RequestError:
            return False
