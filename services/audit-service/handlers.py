"""审计模块 - API 路由处理"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncConnection

from models import SignatureRecord, SessionLog, PermissionDecision, TaskLifecycleEvent, PermissionRequestLog
from log_store import (
    store_signature_record, store_session_log, store_permission_decision,
    store_task_event, store_permission_request_log,
)
from trace_builder import (
    build_task_trace, get_task_sessions, get_agent_history,
    get_task_permission_request_history,
)

router = APIRouter()


async def get_db(request: Request):
    from sqlalchemy.ext.asyncio import AsyncEngine
    engine: AsyncEngine = request.app.state.db_engine
    async with engine.begin() as conn:
        yield conn


# ============================================================
# 写入接口
# ============================================================

@router.post("/audit/signature-records")
async def handle_write_signature_record(
    request: Request,
    conn: AsyncConnection = Depends(get_db),
):
    """POST /audit/signature-records"""
    body = await request.json()
    record = SignatureRecord(**body)
    await store_signature_record(conn, record)
    return {"status": "ok"}


@router.post("/audit/session-logs")
async def handle_write_session_log(
    request: Request,
    conn: AsyncConnection = Depends(get_db),
):
    """POST /audit/session-logs"""
    body = await request.json()
    log = SessionLog(**body)
    await store_session_log(conn, log)
    return {"status": "ok"}


@router.post("/audit/permission-decisions")
async def handle_write_permission_decision(
    request: Request,
    conn: AsyncConnection = Depends(get_db),
):
    """POST /audit/permission-decisions"""
    body = await request.json()
    decision = PermissionDecision(**body)
    await store_permission_decision(conn, decision)
    return {"status": "ok"}


@router.post("/audit/task-events")
async def handle_write_task_event(
    request: Request,
    conn: AsyncConnection = Depends(get_db),
):
    """POST /audit/task-events"""
    body = await request.json()
    event = TaskLifecycleEvent(**body)
    await store_task_event(conn, event)
    return {"status": "ok"}


@router.post("/audit/permission-request-logs")
async def handle_write_permission_request_log(
    request: Request,
    conn: AsyncConnection = Depends(get_db),
):
    """POST /audit/permission-request-logs"""
    body = await request.json()
    log = PermissionRequestLog(**body)
    await store_permission_request_log(conn, log)
    return {"status": "ok"}


# ============================================================
# 查询接口
# ============================================================

@router.get("/audit/tasks/{task_id}/trace")
async def handle_get_task_trace(
    task_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """GET /audit/tasks/{task_id}/trace — 返回完整的树形调用链"""
    trace = await build_task_trace(conn, task_id)
    return trace


@router.get("/audit/tasks/{task_id}/sessions")
async def handle_get_task_sessions(
    task_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """GET /audit/tasks/{task_id}/sessions"""
    sessions = await get_task_sessions(conn, task_id)
    return {"task_id": task_id, "sessions": sessions}


@router.get("/audit/agents/{agent_id}/history")
async def handle_get_agent_history(
    agent_id: str,
    limit: int = 100,
    offset: int = 0,
    conn: AsyncConnection = Depends(get_db),
):
    """GET /audit/agents/{agent_id}/history"""
    result = await get_agent_history(conn, agent_id, limit=limit, offset=offset)
    return result


@router.get("/audit/tasks/{task_id}/permission-requests")
async def handle_get_task_permission_requests(
    task_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """GET /audit/tasks/{task_id}/permission-requests"""
    history = await get_task_permission_request_history(conn, task_id)
    return {"task_id": task_id, "requests": history}
