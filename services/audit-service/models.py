"""审计模块 - Pydantic 数据模型"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 签名记录
# ============================================================

class SignatureRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    session_id: str
    call_id: str
    caller_agent_id: str
    callee_agent_id: str = ""
    mcp_tool_name: str = ""
    request_hash: str = ""
    payload_raw: str = ""
    signature_hex: str = ""
    algorithm: str = "Ed25519"
    signed_at: str = ""
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verified: bool = False


# ============================================================
# 会话日志
# ============================================================

class SessionLog(BaseModel):
    session_id: str
    parent_session_id: Optional[str] = None
    task_id: str
    caller_agent_id: str
    call_type: str
    target_id: str
    tool_owner: str = ""
    depth: int = 0
    decision: str  # "allowed" | "denied"
    deny_reason: Optional[str] = None
    matched_entry_id: Optional[str] = None
    signature_verified: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# 权限判定记录
# ============================================================

class PermissionDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    task_id: str
    caller_agent_id: str
    call_type: str
    target_id: str
    tool_owner: str = ""
    decision: str  # "allowed" | "denied"
    deny_reason: Optional[str] = None
    matched_entry_id: Optional[str] = None
    matched_effect: Optional[str] = None
    token_view_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# 任务生命周期事件
# ============================================================

class TaskLifecycleEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    event_type: str  # "task_started" | "task_finalized"
    triggered_by: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# 权限申请审批日志
# ============================================================

class PermissionRequestLog(BaseModel):
    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    request_id: str
    agent_id: str
    event_type: str  # "requested" | "approved" | "rejected"
    reason: str = ""
    requested_entries: list = Field(default_factory=list)
    approved_entries: list = Field(default_factory=list)
    requested_ttl: int = 0
    approved_ttl: Optional[int] = None
    reviewed_by: Optional[str] = None
    review_comment: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# 响应模型
# ============================================================

class TraceNode(BaseModel):
    """调用链树节点"""
    session_id: str
    call_type: str
    caller_agent_id: str
    target_id: str
    tool_owner: str = ""
    depth: int = 0
    decision: str
    created_at: str
    children: list["TraceNode"] = Field(default_factory=list)


class TaskTraceResponse(BaseModel):
    """任务调用链响应"""
    task_id: str
    root_sessions: list[TraceNode] = Field(default_factory=list)


class SessionLogResponse(BaseModel):
    """会话日志查询响应"""
    session_id: str
    parent_session_id: Optional[str]
    task_id: str
    caller_agent_id: str
    call_type: str
    target_id: str
    depth: int
    decision: str
    created_at: str


class AgentHistoryResponse(BaseModel):
    """Agent 历史行为响应"""
    agent_id: str
    total: int
    sessions: list[SessionLogResponse]
