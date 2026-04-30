"""权限网关 - 权限申请与审批 PG 存储层"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import text

from models import PermissionRequest, RequestStatus


async def create_permission_request(
    conn: AsyncConnection, req: PermissionRequest
) -> PermissionRequest:
    """Agent 提交权限申请。"""
    import json
    await conn.execute(
        text("""
            INSERT INTO permission_requests (id, task_id, agent_id, reason, status,
                                              requested_entries, approved_entries,
                                              requested_ttl, approved_ttl,
                                              reviewed_by, review_comment,
                                              created_at, reviewed_at)
            VALUES (:id, :task_id, :agent_id, :reason, :status,
                    :requested_entries, :approved_entries,
                    :requested_ttl, :approved_ttl,
                    :reviewed_by, :review_comment,
                    :created_at, :reviewed_at)
        """),
        {
            "id": req.request_id,
            "task_id": req.task_id,
            "agent_id": req.agent_id,
            "reason": req.reason,
            "status": req.status.value,
            "requested_entries": json.dumps(
                [e.model_dump(mode="json") for e in req.requested_entries]
            ),
            "approved_entries": json.dumps([]),
            "requested_ttl": req.requested_ttl,
            "approved_ttl": req.approved_ttl,
            "reviewed_by": req.reviewed_by,
            "review_comment": req.review_comment,
            "created_at": req.created_at,
            "reviewed_at": req.reviewed_at,
        },
    )
    return req


async def get_permission_request(
    conn: AsyncConnection, req_id: str
) -> Optional[PermissionRequest]:
    """查询单个申请。"""
    result = await conn.execute(
        text("SELECT * FROM permission_requests WHERE id = :id"),
        {"id": req_id},
    )
    row = result.fetchone()
    if row is None:
        return None
    return _row_to_request(row)


async def list_permission_requests(
    conn: AsyncConnection, task_id: str, status: Optional[str] = None
) -> list[PermissionRequest]:
    """列出任务的权限申请。"""
    if status:
        result = await conn.execute(
            text("SELECT * FROM permission_requests WHERE task_id = :task_id AND status = :status ORDER BY created_at DESC"),
            {"task_id": task_id, "status": status},
        )
    else:
        result = await conn.execute(
            text("SELECT * FROM permission_requests WHERE task_id = :task_id ORDER BY created_at DESC"),
            {"task_id": task_id},
        )
    rows = result.fetchall()
    return [_row_to_request(r) for r in rows]


async def approve_permission_request(
    conn: AsyncConnection,
    req_id: str,
    reviewer: str,
    approved_entries_json: str,
    ttl: int,
    comment: str,
) -> None:
    """审批通过权限申请。"""
    now = datetime.now(timezone.utc)
    await conn.execute(
        text("""
            UPDATE permission_requests
            SET status = 'approved', approved_entries = :approved_entries,
                approved_ttl = :ttl, reviewed_by = :reviewer,
                review_comment = :comment, reviewed_at = :now
            WHERE id = :id
        """),
        {
            "id": req_id,
            "approved_entries": approved_entries_json,
            "ttl": ttl,
            "reviewer": reviewer,
            "comment": comment,
            "now": now,
        },
    )


async def reject_permission_request(
    conn: AsyncConnection, req_id: str, reviewer: str, comment: str
) -> None:
    """拒绝权限申请。"""
    now = datetime.now(timezone.utc)
    await conn.execute(
        text("""
            UPDATE permission_requests
            SET status = 'rejected', reviewed_by = :reviewer,
                review_comment = :comment, reviewed_at = :now
            WHERE id = :id
        """),
        {"id": req_id, "reviewer": reviewer, "comment": comment, "now": now},
    )


def _row_to_request(r) -> PermissionRequest:
    import json
    return PermissionRequest(
        request_id=str(r.id),
        task_id=str(r.task_id),
        agent_id=str(r.agent_id),
        reason=r.reason or "",
        status=RequestStatus(r.status),
        requested_entries=json.loads(r.requested_entries) if isinstance(r.requested_entries, str) else r.requested_entries,
        approved_entries=json.loads(r.approved_entries) if isinstance(r.approved_entries, str) else r.approved_entries,
        requested_ttl=r.requested_ttl,
        approved_ttl=r.approved_ttl,
        reviewed_by=r.reviewed_by,
        review_comment=r.review_comment or "",
        created_at=r.created_at,
        reviewed_at=r.reviewed_at,
    )
