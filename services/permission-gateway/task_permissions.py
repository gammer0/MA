"""权限网关 - 任务临时权限 PG 存储层"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import text

from models import TaskPermissionEntry, TokenEffect, ObjectType, PermissionSource


async def add_task_permission(
    conn: AsyncConnection, entry: TaskPermissionEntry
) -> TaskPermissionEntry:
    """添加任务临时权限条目。"""
    await conn.execute(
        text("""
            INSERT INTO task_permission_entries (id, task_id, agent_id, effect,
                                                  object_type, object_id, tool_owner,
                                                  source, source_request_id, expires_at, created_at)
            VALUES (:id, :task_id, :agent_id, :effect,
                    :object_type, :object_id, :tool_owner,
                    :source, :source_request_id, :expires_at, :created_at)
        """),
        {
            "id": entry.entry_id,
            "task_id": entry.task_id,
            "agent_id": entry.agent_id,
            "effect": entry.effect.value,
            "object_type": entry.object_type.value,
            "object_id": entry.object_id,
            "tool_owner": entry.tool_owner,
            "source": entry.source.value,
            "source_request_id": entry.source_request_id,
            "expires_at": entry.expires_at,
            "created_at": entry.created_at,
        },
    )
    return entry


async def get_task_permissions(
    conn: AsyncConnection, task_id: str, agent_id: Optional[str] = None
) -> list[TaskPermissionEntry]:
    """查询任务的临时权限，可按 Agent 过滤。"""
    if agent_id:
        result = await conn.execute(
            text("""
                SELECT * FROM task_permission_entries
                WHERE task_id = :task_id AND agent_id = :agent_id
                ORDER BY created_at
            """),
            {"task_id": task_id, "agent_id": agent_id},
        )
    else:
        result = await conn.execute(
            text("""
                SELECT * FROM task_permission_entries
                WHERE task_id = :task_id ORDER BY created_at
            """),
            {"task_id": task_id},
        )
    rows = result.fetchall()
    return [_row_to_entry(r) for r in rows]


async def delete_task_permission(conn: AsyncConnection, entry_id: str) -> None:
    """删除单条临时权限。"""
    await conn.execute(
        text("DELETE FROM task_permission_entries WHERE id = :id"),
        {"id": entry_id},
    )


async def delete_all_task_permissions(conn: AsyncConnection, task_id: str) -> int:
    """删除任务的所有临时权限（finalize 时调用）。返回删除数。"""
    result = await conn.execute(
        text("DELETE FROM task_permission_entries WHERE task_id = :task_id"),
        {"task_id": task_id},
    )
    return result.rowcount


def _row_to_entry(r) -> TaskPermissionEntry:
    return TaskPermissionEntry(
        entry_id=str(r.id),
        task_id=str(r.task_id),
        agent_id=str(r.agent_id),
        effect=TokenEffect(r.effect),
        object_type=ObjectType(r.object_type),
        object_id=r.object_id,
        tool_owner=r.tool_owner,
        source=PermissionSource(r.source),
        source_request_id=str(r.source_request_id) if r.source_request_id else None,
        expires_at=r.expires_at,
        created_at=r.created_at,
    )
