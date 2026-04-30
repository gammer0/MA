"""身份注册服务 - Ed25519 加密操作模块"""
import json
import hashlib
from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import HexEncoder
from nacl.exceptions import BadSignatureError

# PyNaCl >= 1.5 不再有 PEMEncoder，使用原生字节方式
import base64


def _private_key_to_pem(signing_key: SigningKey) -> str:
    """将 SigningKey 转为 PEM 字符串"""
    raw = signing_key.encode()
    b64 = base64.b64encode(raw).decode("ascii")
    # 分行（每64字符）
    lines = [b64[i:i+64] for i in range(0, len(b64), 64)]
    return "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"


def _public_key_to_pem(verify_key: VerifyKey) -> str:
    """将 VerifyKey 转为 PEM 字符串"""
    raw = verify_key.encode()
    b64 = base64.b64encode(raw).decode("ascii")
    lines = [b64[i:i+64] for i in range(0, len(b64), 64)]
    return "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----\n"


def _private_key_from_pem(pem_str: str) -> SigningKey:
    """从 PEM 字符串解析 SigningKey"""
    # 去掉头尾标记
    body = pem_str.replace("-----BEGIN PRIVATE KEY-----", "")
    body = body.replace("-----END PRIVATE KEY-----", "")
    body = body.replace("\n", "").replace("\r", "")
    raw = base64.b64decode(body)
    return SigningKey(raw)


def _public_key_from_pem(pem_str: str) -> VerifyKey:
    """从 PEM 字符串解析 VerifyKey"""
    body = pem_str.replace("-----BEGIN PUBLIC KEY-----", "")
    body = body.replace("-----END PUBLIC KEY-----", "")
    body = body.replace("\n", "").replace("\r", "")
    raw = base64.b64decode(body)
    return VerifyKey(raw)


def generate_ed25519_keypair() -> tuple[str, str]:
    """
    生成 Ed25519 密钥对。
    Returns:
        (private_key_pem: str, public_key_pem: str)
    """
    signing_key = SigningKey.generate()
    private_key_pem = _private_key_to_pem(signing_key)
    verify_key = signing_key.verify_key
    public_key_pem = _public_key_to_pem(verify_key)
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
    signing_key = _private_key_from_pem(private_key_pem)
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
        verify_key = _public_key_from_pem(public_key_pem)
        signature_bytes = bytes.fromhex(signature_hex)
        verify_key.verify(payload, signature_bytes)
        return True
    except (BadSignatureError, ValueError):
        return False
