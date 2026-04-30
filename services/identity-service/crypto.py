"""身份注册服务 - Ed25519 加密操作模块"""
import json
import hashlib
from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import PEMEncoder, HexEncoder
from nacl.exceptions import BadSignatureError


def generate_ed25519_keypair() -> tuple[str, str]:
    """
    生成 Ed25519 密钥对。
    Returns:
        (private_key_pem: str, public_key_pem: str)
    """
    signing_key = SigningKey.generate()
    private_key_pem = signing_key.encode(encoder=PEMEncoder).decode("utf-8")
    verify_key = signing_key.verify_key
    public_key_pem = verify_key.encode(encoder=PEMEncoder).decode("utf-8")
    return private_key_pem, public_key_pem


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
    """
    构造签名的规范化 payload（JSON 序列化后的 UTF-8 字节）。
    此函数同时用于 Agent 侧签名和服务端验签，必须完全一致。

    签名内容：
        agent_id + session_id + call_id + timestamp + request_hash
        + callee_agent_id + mcp_tool_name + tool_owner
    """
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
    # 按 key 排序保证规范化
    return json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")


def sign_payload(payload: bytes, private_key_pem: str) -> str:
    """
    使用 Ed25519 私钥对 payload 签名。
    Returns:
        signature_hex: str  # 十六进制字符串（128字符）
    此函数在 Agent 侧 SDK 中运行。
    """
    signing_key = SigningKey(private_key_pem, encoder=PEMEncoder)
    signed = signing_key.sign(payload)
    return signed.signature.hex()


def verify_signature(payload: bytes, signature_hex: str, public_key_pem: str) -> bool:
    """
    使用 Ed25519 公钥验证签名。
    此函数在身份注册服务侧运行。
    Returns:
        True if signature is valid, False otherwise.
    """
    try:
        verify_key = VerifyKey(public_key_pem, encoder=PEMEncoder)
        signature_bytes = bytes.fromhex(signature_hex)
        verify_key.verify(payload, signature_bytes)
        return True
    except (BadSignatureError, ValueError):
        return False
