"""审计模块 - 日志持久化"""
import json

from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import text

from models import SignatureRecord, SessionLog, PermissionDecision, TaskLifecycleEvent, PermissionRequestLog


async def store_signature_record(conn: AsyncConnection, record: SignatureRecord) -> None:
    """写入签名记录。"""
    await conn.execute(
        text("""
            INSERT INTO signature_records (id, task_id, session_id, call_id,
                caller_agent_id, callee_agent_id, mcp_tool_name, request_hash,
                payload_raw, signature_hex, algorithm, signed_at, recorded_at, verified)
            VALUES (:id, :task_id, :session_id, :call_id,
                :caller_agent_id, :callee_agent_id, :mcp_tool_name, :request_hash,
                :payload_raw, :signature_hex, :algorithm, :signed_at, :recorded_at, :verified)
        """),
        {
            "id": record.record_id,
            "task_id": record.task_id,
            "session_id": record.session_id,
            "call_id": record.call_id,
            "caller_agent_id": record.caller_agent_id,
            "callee_agent_id": record.callee_agent_id,
            "mcp_tool_name": record.mcp_tool_name,
            "request_hash": record.request_hash,
            "payload_raw": record.payload_raw,
            "signature_hex": record.signature_hex,
            "algorithm": record.algorithm,
            "signed_at": record.signed_at,
            "recorded_at": record.recorded_at,
            "verified": record.verified,
        },
    )


async def store_session_log(conn: AsyncConnection, log: SessionLog) -> None:
    """写入会话日志。"""
    await conn.execute(
        text("""
            INSERT INTO session_logs (session_id, parent_session_id, task_id,
                caller_agent_id, call_type, target_id, tool_owner, depth,
                decision, deny_reason, matched_entry_id, signature_verified, created_at)
            VALUES (:session_id, :parent_session_id, :task_id,
                :caller_agent_id, :call_type, :target_id, :tool_owner, :depth,
                :decision, :deny_reason, :matched_entry_id, :signature_verified, :created_at)
        """),
        {
            "session_id": log.session_id,
            "parent_session_id": log.parent_session_id,
            "task_id": log.task_id,
            "caller_agent_id": log.caller_agent_id,
            "call_type": log.call_type,
            "target_id": log.target_id,
            "tool_owner": log.tool_owner,
            "depth": log.depth,
            "decision": log.decision,
            "deny_reason": log.deny_reason,
            "matched_entry_id": log.matched_entry_id,
            "signature_verified": log.signature_verified,
            "created_at": log.created_at,
        },
    )


async def store_permission_decision(conn: AsyncConnection, decision: PermissionDecision) -> None:
    """写入权限判定记录。"""
    await conn.execute(
        text("""
            INSERT INTO permission_decisions (id, session_id, task_id,
                caller_agent_id, call_type, target_id, tool_owner,
                decision, deny_reason, matched_entry_id, matched_effect,
                token_view_id, created_at)
            VALUES (:id, :session_id, :task_id,
                :caller_agent_id, :call_type, :target_id, :tool_owner,
                :decision, :deny_reason, :matched_entry_id, :matched_effect,
                :token_view_id, :created_at)
        """),
        {
            "id": decision.decision_id,
            "session_id": decision.session_id,
            "task_id": decision.task_id,
            "caller_agent_id": decision.caller_agent_id,
            "call_type": decision.call_type,
            "target_id": decision.target_id,
            "tool_owner": decision.tool_owner,
            "decision": decision.decision,
            "deny_reason": decision.deny_reason,
            "matched_entry_id": decision.matched_entry_id,
            "matched_effect": decision.matched_effect,
            "token_view_id": decision.token_view_id,
            "created_at": decision.created_at,
        },
    )


async def store_task_event(conn: AsyncConnection, event: TaskLifecycleEvent) -> None:
    """写入任务生命周期事件。"""
    await conn.execute(
        text("""
            INSERT INTO task_lifecycle_events (id, task_id, event_type,
                triggered_by, metadata, created_at)
            VALUES (:id, :task_id, :event_type,
                :triggered_by, :metadata, :created_at)
        """),
        {
            "id": event.event_id,
            "task_id": event.task_id,
            "event_type": event.event_type,
            "triggered_by": event.triggered_by,
            "metadata": json.dumps(event.metadata),
            "created_at": event.created_at,
        },
    )


async def store_permission_request_log(conn: AsyncConnection, log: PermissionRequestLog) -> None:
    """写入权限申请审批日志。"""
    await conn.execute(
        text("""
            INSERT INTO permission_request_logs (id, task_id, request_id,
                agent_id, event_type, reason, requested_entries, approved_entries,
                requested_ttl, approved_ttl, reviewed_by, review_comment, created_at)
            VALUES (:id, :task_id, :request_id,
                :agent_id, :event_type, :reason, :requested_entries, :approved_entries,
                :requested_ttl, :approved_ttl, :reviewed_by, :review_comment, :created_at)
        """),
        {
            "id": log.log_id,
            "task_id": log.task_id,
            "request_id": log.request_id,
            "agent_id": log.agent_id,
            "event_type": log.event_type,
            "reason": log.reason,
            "requested_entries": json.dumps(log.requested_entries),
            "approved_entries": json.dumps(log.approved_entries),
            "requested_ttl": log.requested_ttl,
            "approved_ttl": log.approved_ttl,
            "reviewed_by": log.reviewed_by,
            "review_comment": log.review_comment,
            "created_at": log.created_at,
        },
    )
