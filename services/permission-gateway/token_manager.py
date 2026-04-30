"""权限网关 - Standard Token PG 存储层"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import text

from models import StandardToken, TokenEntry, TokenEffect, ObjectType, TokenStatus


async def create_token(conn: AsyncConnection, token: StandardToken) -> StandardToken:
    """创建长期令牌，写入 PG。"""
    await conn.execute(
        text("""
            INSERT INTO standard_tokens (id, agent_id, label, status, created_at)
            VALUES (:id, :agent_id, :label, :status, :created_at)
        """),
        {
            "id": token.token_id,
            "agent_id": token.agent_id,
            "label": token.label,
            "status": token.status.value,
            "created_at": token.created_at,
        },
    )
    # 写入条目
    for entry in token.entries:
        entry.token_id = token.token_id
        await _insert_entry(conn, entry)
    return token


async def get_token(conn: AsyncConnection, token_id: str) -> Optional[StandardToken]:
    """按 ID 查询令牌及所有条目。"""
    result = await conn.execute(
        text("SELECT * FROM standard_tokens WHERE id = :id"),
        {"id": token_id},
    )
    row = result.fetchone()
    if row is None:
        return None

    entries = await _get_entries(conn, token_id)
    return StandardToken(
        token_id=str(row.id),
        agent_id=str(row.agent_id),
        label=row.label,
        entries=entries,
        status=TokenStatus(row.status),
        created_at=row.created_at,
        revoked_at=row.revoked_at,
    )


async def list_tokens(
    conn: AsyncConnection, agent_id: Optional[str] = None
) -> list[StandardToken]:
    """按 Agent 列出令牌。"""
    if agent_id:
        result = await conn.execute(
            text("SELECT * FROM standard_tokens WHERE agent_id = :agent_id ORDER BY created_at DESC"),
            {"agent_id": agent_id},
        )
    else:
        result = await conn.execute(
            text("SELECT * FROM standard_tokens ORDER BY created_at DESC")
        )
    rows = result.fetchall()

    tokens = []
    for row in rows:
        entries = await _get_entries(conn, str(row.id))
        tokens.append(StandardToken(
            token_id=str(row.id),
            agent_id=str(row.agent_id),
            label=row.label,
            entries=entries,
            status=TokenStatus(row.status),
            created_at=row.created_at,
            revoked_at=row.revoked_at,
        ))
    return tokens


async def get_agent_standard_tokens(
    conn: AsyncConnection, agent_id: str
) -> list[StandardToken]:
    """获取 Agent 所有 active 状态的 standard tokens 及条目。"""
    result = await conn.execute(
        text("SELECT * FROM standard_tokens WHERE agent_id = :agent_id AND status = 'active'"),
        {"agent_id": agent_id},
    )
    rows = result.fetchall()
    tokens = []
    for row in rows:
        entries = await _get_entries(conn, str(row.id))
        tokens.append(StandardToken(
            token_id=str(row.id),
            agent_id=str(row.agent_id),
            label=row.label,
            entries=entries,
            status=TokenStatus.active,
            created_at=row.created_at,
            revoked_at=row.revoked_at,
        ))
    return tokens


async def revoke_token(conn: AsyncConnection, token_id: str) -> None:
    """吊销令牌（软删除）。"""
    now = datetime.now(timezone.utc)
    await conn.execute(
        text("UPDATE standard_tokens SET status = 'revoked', revoked_at = :now WHERE id = :id"),
        {"id": token_id, "now": now},
    )


async def add_entry(conn: AsyncConnection, token_id: str, entry: TokenEntry) -> TokenEntry:
    """向令牌添加条目。"""
    entry.token_id = token_id
    await _insert_entry(conn, entry)
    return entry


async def list_entries(conn: AsyncConnection, token_id: str) -> list[TokenEntry]:
    """列出令牌所有条目。"""
    return await _get_entries(conn, token_id)


async def remove_entry(conn: AsyncConnection, entry_id: str) -> None:
    """删除单条条目。"""
    await conn.execute(
        text("DELETE FROM standard_token_entries WHERE id = :id"),
        {"id": entry_id},
    )


# ============================================================
# 内部辅助函数
# ============================================================

async def _insert_entry(conn: AsyncConnection, entry: TokenEntry) -> None:
    await conn.execute(
        text("""
            INSERT INTO standard_token_entries (id, token_id, effect, object_type,
                                                 object_id, tool_owner, created_at)
            VALUES (:id, :token_id, :effect, :object_type,
                    :object_id, :tool_owner, :created_at)
        """),
        {
            "id": entry.entry_id,
            "token_id": entry.token_id,
            "effect": entry.effect.value,
            "object_type": entry.object_type.value,
            "object_id": entry.object_id,
            "tool_owner": entry.tool_owner,
            "created_at": entry.created_at,
        },
    )


async def _get_entries(conn: AsyncConnection, token_id: str) -> list[TokenEntry]:
    result = await conn.execute(
        text("SELECT * FROM standard_token_entries WHERE token_id = :token_id ORDER BY created_at"),
        {"token_id": token_id},
    )
    rows = result.fetchall()
    return [
        TokenEntry(
            entry_id=str(r.id),
            token_id=str(r.token_id),
            effect=TokenEffect(r.effect),
            object_type=ObjectType(r.object_type),
            object_id=r.object_id,
            tool_owner=r.tool_owner,
            created_at=r.created_at,
        )
        for r in rows
    ]
