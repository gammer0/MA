"""Agent SDK - Ed25519 签名工具"""
import json
import hashlib
from nacl.signing import SigningKey
from nacl.encoding import PEMEncoder


def build_session_signature_payload(
    agent_id: str,
    session_id: str,
    call_id: str,
    timestamp: str,
    request_body: bytes,
    callee_agent_id: str = "",
    mcp_tool_name: str = "",
    tool_owner: str = "",
) -> bytes:
    """构造签名的规范化 payload。"""
    request_hash = hashlib.sha256(request_body).hexdigest()
    payload = {
        "agent_id": agent_id,
        "session_id": session_id,
        "call_id": call_id,
        "timestamp": timestamp,
        "request_hash": request_hash,
        "callee_agent_id": callee_agent_id,
        "mcp_tool_name": mcp_tool_name,
        "tool_owner": tool_owner,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")


def sign_payload(payload: bytes, private_key_pem: str) -> str:
    """使用 Ed25519 私钥签名，返回十六进制字符串。"""
    signing_key = SigningKey(private_key_pem, encoder=PEMEncoder)
    signed = signing_key.sign(payload)
    return signed.signature.hex()
