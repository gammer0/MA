"""审计模块 - 调用链建模"""
import json
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import text

from models import TraceNode, SessionLog, SessionLogResponse


async def build_task_trace(conn: AsyncConnection, task_id: str) -> dict:
    """
    构建任务的完整调用链树。
    1. 查询 task_id 下所有 session_logs
    2. 按 parent_session_id 组装树形结构
    """
    result = await conn.execute(
        text("""
            SELECT * FROM session_logs
            WHERE task_id = :task_id
            ORDER BY depth, created_at
        """),
        {"task_id": task_id},
    )
    rows = result.fetchall()

    # 构建 node map
    nodes: dict[str, dict] = {}
    for r in rows:
        sid = str(r.session_id)
        nodes[sid] = {
            "session_id": sid,
            "parent_session_id": str(r.parent_session_id) if r.parent_session_id else None,
            "call_type": r.call_type,
            "caller_agent_id": str(r.caller_agent_id),
            "target_id": r.target_id,
            "tool_owner": r.tool_owner or "",
            "depth": r.depth,
            "decision": r.decision,
            "created_at": str(r.created_at),
            "children": [],
        }

    # 组装树
    roots = []
    for sid, node in nodes.items():
        parent = node["parent_session_id"]
        if parent and parent in nodes:
            nodes[parent]["children"].append(node)
        else:
            roots.append(node)

    return {"task_id": task_id, "root_sessions": roots}


async def get_task_sessions(
    conn: AsyncConnection, task_id: str
) -> list[SessionLogResponse]:
    """查询任务的所有会话日志（平铺）。"""
    result = await conn.execute(
        text("""
            SELECT * FROM session_logs
            WHERE task_id = :task_id
            ORDER BY created_at
        """),
        {"task_id": task_id},
    )
    rows = result.fetchall()
    return [
        SessionLogResponse(
            session_id=str(r.session_id),
            parent_session_id=str(r.parent_session_id) if r.parent_session_id else None,
            task_id=str(r.task_id),
            caller_agent_id=str(r.caller_agent_id),
            call_type=r.call_type,
            target_id=r.target_id,
            depth=r.depth,
            decision=r.decision,
            created_at=str(r.created_at),
        )
        for r in rows
    ]


async def get_agent_history(
    conn: AsyncConnection, agent_id: str, limit: int = 100, offset: int = 0
) -> dict:
    """查询 Agent 的历史行为（按时间倒序）。"""
    # 查询总数
    count_result = await conn.execute(
        text("SELECT COUNT(*) as cnt FROM session_logs WHERE caller_agent_id = :agent_id"),
        {"agent_id": agent_id},
    )
    total = count_result.fetchone().cnt

    result = await conn.execute(
        text("""
            SELECT * FROM session_logs
            WHERE caller_agent_id = :agent_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"agent_id": agent_id, "limit": limit, "offset": offset},
    )
    rows = result.fetchall()
    sessions = [
        SessionLogResponse(
            session_id=str(r.session_id),
            parent_session_id=str(r.parent_session_id) if r.parent_session_id else None,
            task_id=str(r.task_id),
            caller_agent_id=str(r.caller_agent_id),
            call_type=r.call_type,
            target_id=r.target_id,
            depth=r.depth,
            decision=r.decision,
            created_at=str(r.created_at),
        )
        for r in rows
    ]
    return {"agent_id": agent_id, "total": total, "sessions": sessions}


async def get_task_permission_request_history(
    conn: AsyncConnection, task_id: str
) -> list[dict]:
    """查询任务的权限申请审批历史。"""
    result = await conn.execute(
        text("""
            SELECT * FROM permission_request_logs
            WHERE task_id = :task_id
            ORDER BY created_at
        """),
        {"task_id": task_id},
    )
    rows = result.fetchall()
    return [
        {
            "log_id": str(r.id),
            "task_id": str(r.task_id),
            "request_id": str(r.request_id),
            "agent_id": str(r.agent_id),
            "event_type": r.event_type,
            "reason": r.reason or "",
            "requested_entries": json.loads(r.requested_entries) if isinstance(r.requested_entries, str) else r.requested_entries,
            "approved_entries": json.loads(r.approved_entries) if isinstance(r.approved_entries, str) else r.approved_entries,
            "requested_ttl": r.requested_ttl,
            "approved_ttl": r.approved_ttl,
            "reviewed_by": r.reviewed_by,
            "review_comment": r.review_comment or "",
            "created_at": str(r.created_at),
        }
        for r in rows
    ]
