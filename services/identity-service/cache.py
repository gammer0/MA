"""身份注册服务 - Redis 缓存层"""
from typing import Optional

from redis.asyncio import Redis


# Redis Key 前缀
AGENT_PUBKEY_PREFIX = "agent:pubkey"


def _agent_pubkey_key(agent_id: str) -> str:
    return f"{AGENT_PUBKEY_PREFIX}:{agent_id}"


async def cache_agent_public_key(
    redis: Redis, agent_id: str, public_key_pem: str, ttl: int
) -> None:
    """将 Agent 公钥缓存到 Redis，TTL 对齐证书有效期（秒）。"""
    key = _agent_pubkey_key(agent_id)
    await redis.set(key, public_key_pem, ex=ttl)


async def get_cached_public_key(
    redis: Redis, agent_id: str
) -> Optional[str]:
    """从 Redis 读取缓存的公钥。返回 None 表示未命中。"""
    key = _agent_pubkey_key(agent_id)
    value = await redis.get(key)
    if value is None:
        return None
    return value.decode("utf-8") if isinstance(value, bytes) else value


async def invalidate_agent_cache(redis: Redis, agent_id: str) -> None:
    """吊销/续期时清除 Redis 缓存。"""
    key = _agent_pubkey_key(agent_id)
    await redis.delete(key)
