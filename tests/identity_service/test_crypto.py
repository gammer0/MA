"""身份注册服务 - crypto 模块测试"""
import pytest
import sys
import importlib.util
from pathlib import Path

identity_path = Path(__file__).parent.parent.parent / "services" / "identity-service"

spec = importlib.util.spec_from_file_location("identity_crypto", identity_path / "crypto.py")
crypto_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crypto_mod)

generate_ed25519_keypair = crypto_mod.generate_ed25519_keypair
build_session_signature_payload = crypto_mod.build_session_signature_payload
sign_payload = crypto_mod.sign_payload
verify_signature = crypto_mod.verify_signature


class TestGenerateKeypair:
    """密钥对生成测试"""

    def test_generates_valid_keypair(self):
        """生成有效的 Ed25519 密钥对"""
        private_pem, public_pem = generate_ed25519_keypair()
        
        assert private_pem.startswith("-----BEGIN PRIVATE KEY-----"), \
            "私钥应该是 PEM 格式"
        assert public_pem.startswith("-----BEGIN PUBLIC KEY-----"), \
            "公钥应该是 PEM 格式"
        assert len(private_pem) > 80, "私钥长度应该合理"
        assert len(public_pem) > 50, "公钥长度应该合理"

    def test_keypair_is_unique(self):
        """每次生成的密钥对应该是唯一的"""
        pk1, pub1 = generate_ed25519_keypair()
        pk2, pub2 = generate_ed25519_keypair()
        
        assert pk1 != pk2, "两次生成的私钥应该不同"
        assert pub1 != pub2, "两次生成的公钥应该不同"


class TestSignatureFlow:
    """签名/验签完整流程测试"""

    def test_sign_and_verify_success(self):
        """签名后验签成功"""
        private_pem, public_pem = generate_ed25519_keypair()
        
        payload = build_session_signature_payload(
            agent_id="agent-test",
            session_id="session-001",
            call_id="call-001",
            timestamp="2026-05-01T10:00:00Z",
            request_body=b'{"action": "test"}',
            callee_agent_id="agent-b",
            mcp_tool_name="",
            tool_owner="",
        )
        
        signature_hex = sign_payload(payload, private_pem)
        
        assert len(signature_hex) == 128, f"Ed25519 签名为 64bytes = 128 hex chars, got {len(signature_hex)}"
        assert verify_signature(payload, signature_hex, public_pem), "验签应该成功"

    def test_verify_fails_with_wrong_key(self):
        """用错误的公钥验签应该失败"""
        private_pem, _ = generate_ed25519_keypair()
        _, wrong_public = generate_ed25519_keypair()
        
        payload = build_session_signature_payload(
            agent_id="agent-test",
            session_id="s-1",
            call_id="c-1",
            timestamp="2026-05-01T10:00:00Z",
            request_body=b"test",
        )
        
        signature_hex = sign_payload(payload, private_pem)
        assert not verify_signature(payload, signature_hex, wrong_public), \
            "用错误公钥验签应该失败"

    def test_verify_fails_with_tampered_payload(self):
        """篡改 payload 后验签应该失败"""
        private_pem, public_pem = generate_ed25519_keypair()
        
        payload = build_session_signature_payload(
            agent_id="agent-test",
            session_id="s-1",
            call_id="c-1",
            timestamp="2026-05-01T10:00:00Z",
            request_body=b"original",
        )
        
        signature_hex = sign_payload(payload, private_pem)
        
        # 篡改 payload
        tampered = build_session_signature_payload(
            agent_id="agent-test",
            session_id="s-1",
            call_id="c-1",
            timestamp="2026-05-01T10:00:00Z",
            request_body=b"tampered!",  # 篡改！
        )
        
        assert not verify_signature(tampered, signature_hex, public_pem), \
            "篡改后的 payload 验签应该失败"

    def test_verify_fails_with_invalid_signature_hex(self):
        """无效的签名 hex 应该返回 False 而非异常"""
        _, public_pem = generate_ed25519_keypair()
        payload = b"test payload"
        
        # 无效 hex
        assert not verify_signature(payload, "zzz", public_pem)
        # 长度不对
        assert not verify_signature(payload, "aabb", public_pem)


class TestPayloadBuilding:
    """Payload 构建测试"""

    def test_payload_is_deterministic(self):
        """相同输入产生相同 payload"""
        p1 = build_session_signature_payload(
            agent_id="a", session_id="s", call_id="c",
            timestamp="t", request_body=b"body",
        )
        p2 = build_session_signature_payload(
            agent_id="a", session_id="s", call_id="c",
            timestamp="t", request_body=b"body",
        )
        assert p1 == p2, "相同输入应产生相同 payload"

    def test_payload_differs_for_different_body(self):
        """不同 request_body 产生不同 payload"""
        p1 = build_session_signature_payload(
            agent_id="a", session_id="s", call_id="c",
            timestamp="t", request_body=b"body1",
        )
        p2 = build_session_signature_payload(
            agent_id="a", session_id="s", call_id="c",
            timestamp="t", request_body=b"body2",
        )
        assert p1 != p2, "不同 body 应产生不同 payload"

    def test_payload_includes_tool_owner(self):
        """payload 应包含 tool_owner 字段"""
        payload = build_session_signature_payload(
            agent_id="a", session_id="s", call_id="c",
            timestamp="t", request_body=b"body",
            tool_owner="public",
        )
        assert b'"tool_owner"' in payload
