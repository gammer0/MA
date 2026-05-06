"""加密密钥存储 — 将 Agent 私钥加密写入本地文件，SDK 启动时自动读取。"""

import os
import json
import base64
from pathlib import Path
from typing import Optional

from nacl.secret import SecretBox
from nacl.utils import random as nacl_random


# 默认密钥文件路径（存储在 agent_sdk 目录下，便于查看和管理）
_sdk_dir = Path(__file__).parent.resolve()
DEFAULT_KEY_FILE = str(_sdk_dir / "keys.enc")
# 派生密钥的盐文件
DEFAULT_SALT_FILE = str(_sdk_dir / ".salt")


def _derive_key(machine_key: bytes, salt: bytes) -> bytes:
    """从机器级密钥 + 盐派生 NACL SecretBox 密钥（SHA-256 摘要）。"""
    import hashlib
    return hashlib.sha256(machine_key + salt).digest()


def _get_machine_key() -> bytes:
    """获取机器级密钥 — 不同平台取不同标识。
    
    Windows: 使用机器 SID（安全标识符）
    Linux:   使用 /etc/machine-id
    macOS:   使用 IOPlatformUUID
    """
    import sys
    if sys.platform == "win32":
        import subprocess
        try:
            result = subprocess.run(
                ["wmic", "csproduct", "get", "UUID"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
            if len(lines) >= 2:
                return lines[1].encode("utf-8")
        except Exception:
            pass
        # 回退：使用机器名 + 用户目录
        return (os.environ.get("COMPUTERNAME", "unknown") + os.environ.get("USERPROFILE", "")).encode("utf-8")
    elif sys.platform == "linux":
        try:
            return Path("/etc/machine-id").read_text().strip().encode("utf-8")
        except FileNotFoundError:
            pass
    elif sys.platform == "darwin":
        import subprocess
        try:
            result = subprocess.run(
                ["ioreg", "-d2", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.split("\n"):
                if "IOPlatformUUID" in line:
                    uuid_str = line.split('"')[3]
                    return uuid_str.encode("utf-8")
        except Exception:
            pass
    # 最终回退：使用 hostname
    import socket
    return socket.gethostname().encode("utf-8")


def _ensure_dir(file_path: str):
    """确保密钥文件所在目录存在。"""
    Path(file_path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)


def _load_or_create_salt(salt_path: str) -> bytes:
    """加载或创建盐文件。"""
    salt_file = Path(salt_path)
    if salt_file.exists():
        return salt_file.read_bytes()
    salt = nacl_random(SecretBox.NONCE_SIZE)
    _ensure_dir(salt_path)
    salt_file.write_bytes(salt)
    # Windows 上无法设置 Unix 权限，跳过
    if os.name != "nt":
        salt_file.chmod(0o600)
    return salt


def save_keys(keys: dict, key_file: str = DEFAULT_KEY_FILE, salt_file: str = DEFAULT_SALT_FILE):
    """加密保存 Agent 密钥到本地文件。
    
    keys: { agent_name: {"agent_id": str, "private_key": str}, ... }
    """
    machine_key = _get_machine_key()
    salt = _load_or_create_salt(salt_file)
    box = SecretBox(_derive_key(machine_key, salt))

    plaintext = json.dumps(keys, ensure_ascii=False).encode("utf-8")
    encrypted = box.encrypt(plaintext)

    _ensure_dir(key_file)
    Path(key_file).write_bytes(encrypted)
    if os.name != "nt":
        Path(key_file).chmod(0o600)


def load_keys(key_file: str = DEFAULT_KEY_FILE, salt_file: str = DEFAULT_SALT_FILE) -> dict:
    """从本地加密文件加载 Agent 密钥。
    
    返回: { agent_name: {"agent_id": str, "private_key": str}, ... }
    文件不存在或解密失败时返回空 dict。
    """
    key_path = Path(key_file)
    salt_path = Path(salt_file)
    if not key_path.exists() or not salt_path.exists():
        return {}

    machine_key = _get_machine_key()
    salt = salt_path.read_bytes()
    box = SecretBox(_derive_key(machine_key, salt))

    try:
        encrypted = key_path.read_bytes()
        decrypted = box.decrypt(encrypted)
        return json.loads(decrypted.decode("utf-8"))
    except Exception:
        # 解密失败（例如机器标识变化），返回空
        return {}


def delete_keys(key_file: str = DEFAULT_KEY_FILE, salt_file: str = DEFAULT_SALT_FILE):
    """删除本地加密密钥文件。"""
    for p in [key_file, salt_file]:
        f = Path(p)
        if f.exists():
            f.unlink()
