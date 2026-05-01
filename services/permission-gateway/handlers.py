"""权限网关 - API 路由处理"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import text
from redis.asyncio import Redis

from config import MAX_TEMP_PERMISSION_TTL, VIEW_CACHE_TTL, IDENTITY_SERVICE_URL, ADMIN_API_KEY
from models import (
    StandardToken, TokenEntry, TokenEffect, ObjectType, TokenStatus,
    TaskPermissionEntry, PermissionSource, CallType, SessionStatus,
    PermissionRequest, RequestStatus, Session, TokenView,
    CreateTokenRequest, AddEntryRequest, AddTaskPermissionRequest,
    CreatePermissionRequestRequest, ApproveRequest, GatewayCallRequest,
    TokenResponse, CreateTokenResponse, EntryResponse, RevokeResponse,
    TaskPermissionResponse, PermissionRequestResponse,
    GatewayCallResponse, TokenViewResponse, FinalizeResponse,
)
from token_manager import (
    create_token, get_token, list_tokens, revoke_token,
    add_entry, list_entries, remove_entry,
)
from task_permissions import (
    add_task_permission, get_task_permissions,
    delete_task_permission, delete_all_task_permissions,
)
from permission_requests import (
    create_permission_request, get_permission_request,
    list_permission_requests, approve_permission_request,
    reject_permission_request,
)
from view_builder import build_agent_view, build_multi_agent_view, evaluate_view, check_temp_permission_denied
from session_manager import (
    create_session, cache_token_view, get_cached_view,
    invalidate_session_view, complete_task_sessions, get_task_active_sessions,
)
from identity_client import verify_signature
from audit_client import (
    send_signature_record, send_session_log,
    send_permission_decision, send_task_event, send_permission_request_log,
)

router = APIRouter()


async def get_db(request: Request):
    from sqlalchemy.ext.asyncio import AsyncEngine
    engine: AsyncEngine = request.app.state.db_engine
    async with engine.begin() as conn:
        yield conn


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


# ============================================================
# Standard Token 管理 API
# ============================================================

@router.post("/tokens", response_model=CreateTokenResponse)
async def handle_create_token(
    request: CreateTokenRequest,
    conn: AsyncConnection = Depends(get_db),
):
    """POST /tokens"""
    token = StandardToken(
        agent_id=request.agent_id,
        label=request.label,
        entries=request.entries,
    )
    await create_token(conn, token)
    return CreateTokenResponse(token_id=token.token_id)


@router.get("/tokens/{token_id}", response_model=TokenResponse)
async def handle_get_token(
    token_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """GET /tokens/{token_id}"""
    token = await get_token(conn, token_id)
    if token is None:
        raise HTTPException(status_code=404, detail="Token not found")
    return TokenResponse(
        token_id=token.token_id,
        agent_id=token.agent_id,
        label=token.label,
        entries=token.entries,
        status=token.status,
        created_at=token.created_at,
        revoked_at=token.revoked_at,
    )


@router.get("/tokens", response_model=list[TokenResponse])
async def handle_list_tokens(
    agent_id: Optional[str] = None,
    conn: AsyncConnection = Depends(get_db),
):
    """GET /tokens"""
    tokens = await list_tokens(conn, agent_id=agent_id)
    return [
        TokenResponse(
            token_id=t.token_id,
            agent_id=t.agent_id,
            label=t.label,
            entries=t.entries,
            status=t.status,
            created_at=t.created_at,
            revoked_at=t.revoked_at,
        )
        for t in tokens
    ]


@router.delete("/tokens/{token_id}", response_model=RevokeResponse)
async def handle_revoke_token(
    token_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """DELETE /tokens/{token_id}"""
    token = await get_token(conn, token_id)
    if token is None:
        raise HTTPException(status_code=404, detail="Token not found")
    await revoke_token(conn, token_id)
    return RevokeResponse(token_id=token_id, message="Token revoked.")


@router.post("/tokens/{token_id}/entries", response_model=EntryResponse)
async def handle_add_entry(
    token_id: str,
    request: AddEntryRequest,
    conn: AsyncConnection = Depends(get_db),
):
    """POST /tokens/{token_id}/entries"""
    entry = TokenEntry(
        effect=request.effect,
        object_type=request.object_type,
        object_id=request.object_id,
        tool_owner=request.tool_owner,
    )
    result = await add_entry(conn, token_id, entry)
    return EntryResponse(
        entry_id=result.entry_id,
        token_id=token_id,
        effect=result.effect,
        object_type=result.object_type,
        object_id=result.object_id,
        tool_owner=result.tool_owner,
    )


@router.get("/tokens/{token_id}/entries", response_model=list[EntryResponse])
async def handle_list_entries(
    token_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """GET /tokens/{token_id}/entries"""
    entries = await list_entries(conn, token_id)
    return [
        EntryResponse(
            entry_id=e.entry_id,
            token_id=token_id,
            effect=e.effect,
            object_type=e.object_type,
            object_id=e.object_id,
            tool_owner=e.tool_owner,
        )
        for e in entries
    ]


@router.delete("/tokens/{token_id}/entries/{entry_id}")
async def handle_remove_entry(
    token_id: str,
    entry_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """DELETE /tokens/{token_id}/entries/{entry_id}"""
    await remove_entry(conn, entry_id)
    return {"message": "Entry removed."}


# ============================================================
# 任务临时权限 API
# ============================================================

@router.post("/tasks/{task_id}/permissions", response_model=TaskPermissionResponse)
async def handle_add_task_permission(
    task_id: str,
    request: AddTaskPermissionRequest,
    conn: AsyncConnection = Depends(get_db),
):
    """POST /tasks/{task_id}/permissions"""
    ttl = min(request.ttl_seconds, MAX_TEMP_PERMISSION_TTL)
    entry = TaskPermissionEntry(
        task_id=task_id,
        agent_id=request.agent_id,
        effect=request.effect,
        object_type=request.object_type,
        object_id=request.object_id,
        tool_owner=request.tool_owner,
        source=PermissionSource.manual,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
    )
    result = await add_task_permission(conn, entry)
    return TaskPermissionResponse(
        entry_id=result.entry_id,
        task_id=result.task_id,
        agent_id=result.agent_id,
        effect=result.effect,
        object_type=result.object_type,
        object_id=result.object_id,
        tool_owner=result.tool_owner,
        source=result.source,
        expires_at=result.expires_at,
    )


@router.get("/tasks/{task_id}/permissions", response_model=list[TaskPermissionResponse])
async def handle_get_task_permissions(
    task_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """GET /tasks/{task_id}/permissions"""
    entries = await get_task_permissions(conn, task_id)
    return [
        TaskPermissionResponse(
            entry_id=e.entry_id,
            task_id=e.task_id,
            agent_id=e.agent_id,
            effect=e.effect,
            object_type=e.object_type,
            object_id=e.object_id,
            tool_owner=e.tool_owner,
            source=e.source,
            expires_at=e.expires_at,
        )
        for e in entries
    ]


@router.delete("/tasks/{task_id}/permissions/{entry_id}")
async def handle_delete_task_permission(
    task_id: str,
    entry_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """DELETE /tasks/{task_id}/permissions/{entry_id}"""
    await delete_task_permission(conn, entry_id)
    return {"message": "Task permission removed."}


@router.post("/tasks/{task_id}/finalize", response_model=FinalizeResponse)
async def handle_finalize_task(
    task_id: str,
    conn: AsyncConnection = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """POST /tasks/{task_id}/finalize — 任务结束，级联清理"""
    # 获取活跃会话列表
    session_ids = await get_task_active_sessions(conn, task_id)

    # 清除 Redis 视图缓存
    for sid in session_ids:
        await invalidate_session_view(redis, sid)

    # 标记会话完成
    sessions_completed = await complete_task_sessions(conn, task_id)

    # 删除临时权限
    permissions_cleaned = await delete_all_task_permissions(conn, task_id)

    # 审计
    send_task_event({
        "task_id": task_id,
        "event_type": "task_finalized",
        "triggered_by": "system",
        "metadata": {"sessions_completed": sessions_completed, "permissions_cleaned": permissions_cleaned},
    })

    return FinalizeResponse(
        task_id=task_id,
        sessions_completed=sessions_completed,
        permissions_cleaned=permissions_cleaned,
    )


# ============================================================
# 权限申请与审批 API
# ============================================================

@router.post("/tasks/{task_id}/permission-requests", response_model=PermissionRequestResponse)
async def handle_create_permission_request(
    task_id: str,
    request: CreatePermissionRequestRequest,
    conn: AsyncConnection = Depends(get_db),
):
    """POST /tasks/{task_id}/permission-requests"""
    req = PermissionRequest(
        task_id=task_id,
        agent_id=request.agent_id,
        reason=request.reason,
        requested_entries=[TokenEntry(**e) for e in request.requested_entries],
        requested_ttl=min(request.ttl_seconds, MAX_TEMP_PERMISSION_TTL),
    )
    await create_permission_request(conn, req)

    # 审计
    send_permission_request_log({
        "task_id": task_id,
        "request_id": req.request_id,
        "agent_id": req.agent_id,
        "event_type": "requested",
        "reason": req.reason,
        "requested_entries": [e.model_dump(mode="json") for e in req.requested_entries],
        "requested_ttl": req.requested_ttl,
    })

    return PermissionRequestResponse(
        request_id=req.request_id,
        task_id=req.task_id,
        agent_id=req.agent_id,
        reason=req.reason,
        status=req.status,
        requested_entries=[e.model_dump(mode="json") for e in req.requested_entries],
        approved_entries=[],
        requested_ttl=req.requested_ttl,
        approved_ttl=None,
        reviewed_by=None,
        review_comment=None,
        created_at=req.created_at,
        reviewed_at=None,
    )


@router.get("/tasks/{task_id}/permission-requests", response_model=list[PermissionRequestResponse])
async def handle_list_permission_requests(
    task_id: str,
    status: Optional[str] = None,
    conn: AsyncConnection = Depends(get_db),
):
    """GET /tasks/{task_id}/permission-requests"""
    reqs = await list_permission_requests(conn, task_id, status=status)
    return [
        PermissionRequestResponse(
            request_id=r.request_id,
            task_id=r.task_id,
            agent_id=r.agent_id,
            reason=r.reason,
            status=r.status,
            requested_entries=r.requested_entries if isinstance(r.requested_entries, list) else [],
            approved_entries=r.approved_entries if isinstance(r.approved_entries, list) else [],
            requested_ttl=r.requested_ttl,
            approved_ttl=r.approved_ttl,
            reviewed_by=r.reviewed_by,
            review_comment=r.review_comment,
            created_at=r.created_at,
            reviewed_at=r.reviewed_at,
        )
        for r in reqs
    ]


@router.get("/tasks/{task_id}/permission-requests/{req_id}", response_model=PermissionRequestResponse)
async def handle_get_permission_request(
    task_id: str,
    req_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """GET /tasks/{task_id}/permission-requests/{req_id}"""
    req = await get_permission_request(conn, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return PermissionRequestResponse(
        request_id=req.request_id,
        task_id=req.task_id,
        agent_id=req.agent_id,
        reason=req.reason,
        status=req.status,
        requested_entries=[e.model_dump(mode="json") if hasattr(e, 'model_dump') else e for e in (req.requested_entries if isinstance(req.requested_entries, list) else [])],
        approved_entries=[e.model_dump(mode="json") if hasattr(e, 'model_dump') else e for e in (req.approved_entries if isinstance(req.approved_entries, list) else [])],
        requested_ttl=req.requested_ttl,
        approved_ttl=req.approved_ttl,
        reviewed_by=req.reviewed_by,
        review_comment=req.review_comment,
        created_at=req.created_at,
        reviewed_at=req.reviewed_at,
    )


@router.post("/tasks/{task_id}/permission-requests/{req_id}/approve")
async def handle_approve_permission_request(
    task_id: str,
    req_id: str,
    request: ApproveRequest,
    conn: AsyncConnection = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """POST /tasks/{task_id}/permission-requests/{req_id}/approve"""
    req = await get_permission_request(conn, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != RequestStatus.pending_approval:
        raise HTTPException(status_code=400, detail="Request is not pending approval")

    if request.action == "reject":
        await reject_permission_request(conn, req_id, "admin", request.comment)
        send_permission_request_log({
            "task_id": task_id,
            "request_id": req_id,
            "agent_id": req.agent_id,
            "event_type": "rejected",
            "reviewed_by": "admin",
            "review_comment": request.comment,
        })
        return {"message": "Permission request rejected."}

    if request.action == "approve" or request.action == "auto_approve":
        # 裁剪 TTL
        ttl = min(request.ttl_seconds, req.requested_ttl, MAX_TEMP_PERMISSION_TTL)
        approved_json = json.dumps(request.approved_entries)

        reviewer = "admin" if request.action == "approve" else "auto_approve"
        comment = request.comment or ("[降级] 自动批准（原需人工审批）" if request.action == "auto_approve" else "")

        # 检查申请条目是否被 deny 覆盖
        denied = await check_temp_permission_denied(conn, req.agent_id, task_id, request.approved_entries)
        if denied:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot approve: entry '{denied}' is explicitly denied by existing token."
            )

        await approve_permission_request(conn, req_id, reviewer, approved_json, ttl, comment)

        # 创建 TaskPermissionEntry
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        for e in request.approved_entries:
            entry = TaskPermissionEntry(
                task_id=task_id,
                agent_id=req.agent_id,
                effect=TokenEffect(e.get("effect", "allow")),
                object_type=ObjectType(e.get("object_type", "mcp_tool")),
                object_id=e.get("object_id", ""),
                tool_owner=e.get("tool_owner", ""),
                source=PermissionSource.request_approved,
                source_request_id=req_id,
                expires_at=expires_at,
            )
            await add_task_permission(conn, entry)

        # 清除 Redis 视图缓存
        session_ids = await get_task_active_sessions(conn, task_id)
        for sid in session_ids:
            await invalidate_session_view(redis, sid)

        # 审计
        send_permission_request_log({
            "task_id": task_id,
            "request_id": req_id,
            "agent_id": req.agent_id,
            "event_type": "approved",
            "approved_entries": request.approved_entries,
            "approved_ttl": ttl,
            "reviewed_by": reviewer,
            "review_comment": comment,
        })

        return {"message": "Permission request approved.", "ttl": ttl, "approval_mode": request.action}

    raise HTTPException(status_code=400, detail="Invalid action")


# ============================================================
# 运行时 API — 统一调用入口
# ============================================================

@router.post("/gateway/call", response_model=GatewayCallResponse)
async def handle_gateway_call(
    request: GatewayCallRequest,
    gateway_request: Request,
    conn: AsyncConnection = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    POST /gateway/call — 完整拦截流程:
    验签 → 自调用检查 → 视图构建 → 判定 → 审计
    """
    # ① 解析请求头
    agent_id = gateway_request.headers.get("X-Agent-Id", "")
    session_id = gateway_request.headers.get("X-Session-Id", str(uuid.uuid4()))
    call_id = gateway_request.headers.get("X-Call-Id", str(uuid.uuid4()))
    signature_hex = gateway_request.headers.get("X-Signature-Hex", "")
    timestamp = gateway_request.headers.get("X-Timestamp", "")

    if not agent_id:
        raise HTTPException(status_code=400, detail="Missing X-Agent-Id")

    # ② 身份验证
    # 使用json.dumps保证与SDK端完全一致的序列化（包括key顺序和空字段）
    request_body = json.dumps(request.model_dump(), sort_keys=True, ensure_ascii=False)
    verified = await verify_signature(
        agent_id=agent_id,
        session_id=session_id,
        call_id=call_id,
        timestamp=timestamp,
        request_body=request_body,
        signature_hex=signature_hex,
        callee_agent_id=request.callee_agent_id,
        mcp_tool_name=request.tool_name,
        tool_owner=request.tool_owner,
    )

    send_signature_record({
        "task_id": request.task_id or "",
        "session_id": session_id,
        "call_id": call_id,
        "caller_agent_id": agent_id,
        "callee_agent_id": request.callee_agent_id,
        "mcp_tool_name": request.tool_name,
        "request_hash": "",
        "payload_raw": request_body,
        "signature_hex": signature_hex,
        "algorithm": "Ed25519",
        "signed_at": timestamp,
        "verified": verified,
    })

    if not verified:
        return GatewayCallResponse(
            status="denied",
            reason="unauthorized",
            session_id=session_id,
            message="Signature verification failed.",
        )

    # ③ 自调用检查
    if request.call_type == "a2a" and agent_id == request.callee_agent_id:
        return GatewayCallResponse(
            status="denied",
            reason="self_call",
            can_request=False,
            session_id=session_id,
            message="A2A self-call is not allowed.",
        )

    # ④ 获取/构建令牌视图
    view = await get_cached_view(redis, session_id)
    if view is None:
        if request.call_type == "a2a":
            view = await build_multi_agent_view(
                conn, agent_id, request.callee_agent_id, request.task_id
            )
        else:
            view = await build_agent_view(conn, agent_id, request.task_id)
        view.session_id = session_id
        await cache_token_view(redis, session_id, view, VIEW_CACHE_TTL)

    # ⑤ 权限判定
    target_id = request.callee_agent_id if request.call_type == "a2a" else request.tool_name
    decision, matched_id = evaluate_view(
        view, request.call_type, target_id, request.tool_owner
    )

    # ⑥ 审计
    deny_reason = None
    if decision == "explicitly_denied":
        deny_reason = "explicitly_denied"
    elif decision == "permission_required":
        deny_reason = "permission_required"

    send_session_log({
        "session_id": session_id,
        "parent_session_id": None,
        "task_id": request.task_id or "",
        "caller_agent_id": agent_id,
        "call_type": request.call_type,
        "target_id": target_id,
        "tool_owner": request.tool_owner,
        "depth": 0,
        "decision": "allowed" if decision == "allowed" else "denied",
        "deny_reason": deny_reason,
        "matched_entry_id": matched_id,
        "signature_verified": verified,
    })
    send_permission_decision({
        "session_id": session_id,
        "task_id": request.task_id or "",
        "caller_agent_id": agent_id,
        "call_type": request.call_type,
        "target_id": target_id,
        "tool_owner": request.tool_owner,
        "decision": "allowed" if decision == "allowed" else "denied",
        "deny_reason": deny_reason if deny_reason else ("self_call" if decision != "allowed" else None),
        "matched_entry_id": matched_id,
        "matched_effect": "deny" if decision == "explicitly_denied" else ("allow" if decision == "allowed" else None),
        "token_view_id": view.view_id,
    })

    # ⑦ 返回结果
    if decision == "allowed":
        return GatewayCallResponse(
            status="allowed",
            session_id=session_id,
            message="Access granted.",
        )

    if decision == "explicitly_denied":
        return GatewayCallResponse(
            status="denied",
            reason="explicitly_denied",
            can_request=False,
            session_id=session_id,
            message="Access explicitly denied by deny token.",
        )

    # permission_required
    return GatewayCallResponse(
        status="denied",
        reason="permission_required",
        can_request=True,
        request_permission_url=f"/tasks/{request.task_id}/permission-requests",
        missing_entries=[
            {
                "effect": "allow",
                "object_type": "mcp_tool" if request.call_type == "mcp" else "agent",
                "object_id": target_id,
                "tool_owner": request.tool_owner,
            }
        ],
        session_id=session_id,
        message=request.reason or "Permission required. Submit a permission request.",
    )


@router.get("/sessions/{session_id}/view", response_model=TokenViewResponse)
async def handle_get_session_view(
    session_id: str,
    redis: Redis = Depends(get_redis),
):
    """GET /sessions/{session_id}/view"""
    view = await get_cached_view(redis, session_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Session view not found or expired")
    return TokenViewResponse(
        view_id=view.view_id,
        session_id=session_id,
        agent_id=view.agent_id,
        task_id=view.task_id,
        entries=view.entries,
        built_at=view.built_at,
    )


# ============================================================
# 权限订阅管理 UI
# ============================================================

@router.post("/tasks/{task_id}/instruction")
async def handle_store_task_instruction(
    task_id: str,
    request: Request,
    redis: Redis = Depends(get_redis),
):
    """POST /tasks/{task_id}/instruction — 存储任务指令（执行层调用）。"""
    body = await request.json()
    instruction = body.get("instruction", "")
    await redis.set(f"task:{task_id}:instruction", instruction, ex=86400)
    return {"status": "ok", "task_id": task_id}


@router.get("/admin/task-audit/{task_id}")
async def handle_admin_task_audit(
    task_id: str,
    gateway_request: Request,
    redis: Redis = Depends(get_redis),
):
    """GET /admin/task-audit/{task_id} — 管理员查询任务的完整审计日志。"""
    import httpx
    from sqlalchemy.ext.asyncio import AsyncEngine

    engine: AsyncEngine = gateway_request.app.state.db_engine

    # 1. 获取任务指令
    instruction = await redis.get(f"task:{task_id}:instruction")
    instruction_str = instruction if isinstance(instruction, str) else (instruction.decode("utf-8") if instruction else "")

    result = {
        "task_id": task_id,
        "instruction": instruction_str,
        "trace": None,
        "sessions": [],
        "pending_requests": [],
    }

    # 2. 直接从数据库查询会话日志（绕过 audit-service 的 API bug）
    try:
        async with engine.begin() as conn:
            # 会话日志
            sl_result = await conn.execute(
                text("SELECT session_id, task_id, caller_agent_id, call_type, target_id, "
                     "tool_owner, depth, decision, deny_reason, created_at "
                     "FROM session_logs WHERE task_id = :tid ORDER BY created_at"),
                {"tid": task_id},
            )
            for row in sl_result.fetchall():
                result["sessions"].append({
                    "session_id": str(row.session_id),
                    "task_id": str(row.task_id),
                    "caller_agent_id": str(row.caller_agent_id),
                    "call_type": row.call_type,
                    "target_id": row.target_id,
                    "tool_owner": row.tool_owner or "",
                    "depth": row.depth,
                    "decision": row.decision,
                    "deny_reason": row.deny_reason or "",
                    "created_at": str(row.created_at),
                })

            # 调用链（简单的树形结构：按 depth 分组）
            trace_result = await conn.execute(
                text("SELECT session_id, call_type, caller_agent_id, target_id, "
                     "tool_owner, decision, deny_reason, depth, created_at "
                     "FROM session_logs WHERE task_id = :tid ORDER BY created_at"),
                {"tid": task_id},
            )
            trace_nodes = []
            for row in trace_result.fetchall():
                trace_nodes.append({
                    "session_id": str(row.session_id),
                    "call_type": row.call_type,
                    "caller": str(row.caller_agent_id),
                    "target": row.target_id,
                    "tool_owner": row.tool_owner or "",
                    "decision": row.decision,
                    "deny_reason": row.deny_reason or "",
                    "depth": row.depth,
                    "time": str(row.created_at),
                })
            if trace_nodes:
                result["trace"] = {"task_id": task_id, "steps": trace_nodes}
    except Exception:
        pass

    # 3. 本地的权限申请记录
    try:
        async with engine.begin() as conn:
            pr_result = await conn.execute(
                text("SELECT id, agent_id, reason, status, requested_entries, created_at, reviewed_at "
                     "FROM permission_requests WHERE task_id = :tid ORDER BY created_at"),
                {"tid": task_id},
            )
            import json as _json
            for row in pr_result.fetchall():
                result["pending_requests"].append({
                    "request_id": str(row.id),
                    "agent_id": str(row.agent_id),
                    "reason": row.reason or "",
                    "status": row.status,
                    "requested_entries": _json.loads(row.requested_entries) if isinstance(row.requested_entries, str) else row.requested_entries,
                    "created_at": str(row.created_at),
                    "reviewed_at": str(row.reviewed_at) if row.reviewed_at else None,
                })
    except Exception:
        pass

    return result


@router.get("/admin/task-list")
async def handle_admin_task_list(
    page: int = 1,
    page_size: int = 5,
    gateway_request: Request = None,
    redis: Redis = Depends(get_redis),
):
    """GET /admin/task-list?page=1&page_size=5 — 分页任务列表。"""
    import json as _json
    from sqlalchemy.ext.asyncio import AsyncEngine
    engine: AsyncEngine = gateway_request.app.state.db_engine if gateway_request else None

    if engine is None:
        return {"tasks": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 1}

    # 从 session_logs 获取不重复的任务ID和时间
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT DISTINCT task_id, MIN(created_at) as first_call, MAX(created_at) as last_call "
                 "FROM session_logs GROUP BY task_id ORDER BY MIN(created_at) DESC")
        )
        all_tasks = [(str(r.task_id), str(r.first_call), str(r.last_call)) for r in result.fetchall()]

    total = len(all_tasks)
    start = (page - 1) * page_size
    tasks_page = all_tasks[start:start + page_size]

    items = []
    for tid, first_call, last_call in tasks_page:
        instruction = await redis.get(f"task:{tid}:instruction")
        instr_str = instruction if isinstance(instruction, str) else (instruction.decode("utf-8") if instruction else "")
        # 统计会话数
        async with engine.begin() as conn:
            cnt_result = await conn.execute(
                text("SELECT COUNT(*) as cnt FROM session_logs WHERE task_id = :tid"),
                {"tid": tid},
            )
            session_count = cnt_result.fetchone().cnt
        items.append({
            "task_id": tid,
            "instruction": instr_str or "(无指令)",
            "session_count": session_count,
            "first_call": first_call,
            "last_call": last_call,
        })

    return {
        "tasks": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/admin/pending-requests")
async def handle_admin_pending_requests(
    conn: AsyncConnection = Depends(get_db),
):
    """GET /admin/pending-requests — 列出所有待审批的权限申请。"""
    result = await conn.execute(
        text("SELECT * FROM permission_requests WHERE status = 'pending_approval' ORDER BY created_at DESC")
    )
    rows = result.fetchall()
    import json as _json
    return [
        {
            "request_id": str(r.id),
            "task_id": str(r.task_id),
            "agent_id": str(r.agent_id),
            "reason": r.reason or "",
            "status": r.status,
            "requested_entries": _json.loads(r.requested_entries) if isinstance(r.requested_entries, str) else r.requested_entries,
            "requested_ttl": r.requested_ttl,
            "created_at": str(r.created_at),
        }
        for r in rows
    ]


@router.get("/admin/agents")
async def handle_admin_list_agents():
    """GET /admin/agents — 代理到身份注册服务获取 Agent 列表"""
    import httpx
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{IDENTITY_SERVICE_URL}/agents",
                headers={"X-Admin-API-Key": ADMIN_API_KEY},
            )
            return resp.json()
        except Exception:
            return []


@router.get("/admin/tools")
async def handle_admin_list_tools():
    """GET /admin/tools — 代理到身份注册服务获取 Tool 列表"""
    import httpx
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{IDENTITY_SERVICE_URL}/tools",
                headers={"X-Admin-API-Key": ADMIN_API_KEY},
            )
            return resp.json()
        except Exception:
            return []
