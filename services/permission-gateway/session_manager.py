"""权限网关 - 会话管理"""
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import text
from redis.asyncio import Redis

from models import Session, TokenView, SessionStatus

# Redis Key 前缀
SESSION_VIEW_PREFIX = "session"


def _session_view_key(session_id: str) -> str:
    return f"{SESSION_VIEW_PREFIX}:{session_id}:view"


async def create_session(conn: AsyncConnection, session: Session) -> Session:
    """创建会话记录。"""
    await conn.execute(
        text("""
            INSERT INTO sessions (id, task_id, caller_agent_id, call_type,
                                  target_id, tool_owner, token_view_id,
                                  status, created_at)
            VALUES (:id, :task_id, :caller_agent_id, :call_type,
                    :target_id, :tool_owner, :token_view_id,
                    :status, :created_at)
        """),
        {
            "id": session.session_id,
            "task_id": session.task_id,
            "caller_agent_id": session.caller_agent_id,
            "call_type": session.call_type.value,
            "target_id": session.target_id,
            "tool_owner": session.tool_owner,
            "token_view_id": session.token_view_id,
            "status": session.status.value,
            "created_at": session.created_at,
        },
    )
    return session


async def cache_token_view(
    redis: Redis, session_id: str, view: TokenView, ttl: int
) -> None:
    """将会话的令牌视图缓存到 Redis。"""
    key = _session_view_key(session_id)
    value = view.model_dump_json()
    await redis.set(key, value, ex=ttl)


async def get_cached_view(
    redis: Redis, session_id: str
) -> Optional[TokenView]:
    """从 Redis 获取缓存的令牌视图。"""
    key = _session_view_key(session_id)
    value = await redis.get(key)
    if value is None:
        return None
    raw = value.decode("utf-8") if isinstance(value, bytes) else value
    return TokenView.model_validate_json(raw)


async def invalidate_session_views(
    redis: Redis, task_id: str, agent_id: Optional[str] = None
) -> None:
    """
    权限变更时使相关会话的视图缓存失效。
    遍历 Redis 中该任务相关的 session key。
    简化实现：通过 session 列表逐个清除。
    """
    # 注：需要在调用方传入 sessions 列表来逐个清除
    pass


async def invalidate_session_view(redis: Redis, session_id: str) -> None:
    """清除单个会话的视图缓存。"""
    key = _session_view_key(session_id)
    await redis.delete(key)


async def complete_session(conn: AsyncConnection, session_id: str) -> None:
    """标记会话完成。"""
    now = datetime.now(timezone.utc)
    await conn.execute(
        text("UPDATE sessions SET status = 'completed', completed_at = :now WHERE id = :id"),
        {"id": session_id, "now": now},
    )


async def complete_task_sessions(conn: AsyncConnection, task_id: str) -> int:
    """标记任务的所有活跃会话为完成。返回更新数。"""
    now = datetime.now(timezone.utc)
    result = await conn.execute(
        text("""
            UPDATE sessions SET status = 'completed', completed_at = :now
            WHERE task_id = :task_id AND status = 'active'
        """),
        {"task_id": task_id, "now": now},
    )
    return result.rowcount


async def get_task_active_sessions(
    conn: AsyncConnection, task_id: str
) -> list[str]:
    """获取任务所有活跃会话的 session_id 列表。"""
    result = await conn.execute(
        text("SELECT id FROM sessions WHERE task_id = :task_id AND status = 'active'"),
        {"task_id": task_id},
    )
    return [str(r.id) for r in result.fetchall()]
