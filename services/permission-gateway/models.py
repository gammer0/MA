"""权限网关 - Pydantic 数据模型"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 枚举
# ============================================================

class TokenEffect(str, Enum):
    allow = "allow"
    deny = "deny"


class ObjectType(str, Enum):
    agent = "agent"
    mcp_tool = "mcp_tool"


class TokenStatus(str, Enum):
    active = "active"
    revoked = "revoked"


class CallType(str, Enum):
    a2a = "a2a"
    mcp = "mcp"


class SessionStatus(str, Enum):
    active = "active"
    completed = "completed"
    rejected = "rejected"


class RequestStatus(str, Enum):
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"


class PermissionSource(str, Enum):
    manual = "manual"
    request_approved = "request_approved"


# ============================================================
# TokenEntry（权限条目）
# ============================================================

class TokenEntry(BaseModel):
    """权限条目 - 最小管理单元"""
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    token_id: str = ""
    effect: TokenEffect
    object_type: ObjectType
    object_id: str  # 目标 agent_id 或 tool_name，支持 "*"
    tool_owner: str = ""  # MCP 场景："public" | "{agent_id}"；A2A：""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# StandardToken（长期令牌）
# ============================================================

class StandardToken(BaseModel):
    """长期令牌 - 绑定 Agent"""
    token_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    label: str
    entries: list[TokenEntry] = Field(default_factory=list)
    status: TokenStatus = TokenStatus.active
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revoked_at: Optional[datetime] = None


# ============================================================
# TaskPermissionEntry（任务临时权限条目）
# ============================================================

class TaskPermissionEntry(BaseModel):
    """任务临时权限条目 - 绑定 Task + Agent"""
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    agent_id: str
    effect: TokenEffect
    object_type: ObjectType
    object_id: str
    tool_owner: str = ""
    source: PermissionSource = PermissionSource.manual
    source_request_id: Optional[str] = None
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# TokenView（令牌视图）
# ============================================================

class TokenView(BaseModel):
    """令牌视图 - 会话级"""
    view_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    agent_id: str = ""
    task_id: Optional[str] = None
    entries: list[TokenEntry] = Field(default_factory=list)
    built_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# PermissionRequest（权限申请）
# ============================================================

class PermissionRequest(BaseModel):
    """权限申请"""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    agent_id: str
    reason: str = ""
    status: RequestStatus = RequestStatus.pending_approval
    requested_entries: list[TokenEntry] = Field(default_factory=list)
    approved_entries: list[TokenEntry] = Field(default_factory=list)
    requested_ttl: int = 600
    approved_ttl: Optional[int] = None
    reviewed_by: Optional[str] = None
    review_comment: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None


# ============================================================
# Session（会话）
# ============================================================

class Session(BaseModel):
    """会话"""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: Optional[str] = None
    caller_agent_id: str
    call_type: CallType
    target_id: str
    tool_owner: str = ""
    token_view_id: Optional[str] = None
    status: SessionStatus = SessionStatus.active
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


# ============================================================
# 请求模型
# ============================================================

class CreateTokenRequest(BaseModel):
    """POST /tokens"""
    agent_id: str
    label: str
    entries: list[TokenEntry]


class AddEntryRequest(BaseModel):
    """POST /tokens/{id}/entries"""
    effect: TokenEffect
    object_type: ObjectType
    object_id: str
    tool_owner: str = ""


class AddTaskPermissionRequest(BaseModel):
    """POST /tasks/{id}/permissions"""
    agent_id: str
    effect: TokenEffect
    object_type: ObjectType
    object_id: str
    tool_owner: str = ""
    ttl_seconds: int = 3600


class CreatePermissionRequestRequest(BaseModel):
    """POST /tasks/{id}/permission-requests"""
    agent_id: str
    reason: str
    requested_entries: list[dict]
    ttl_seconds: int = 600


class ApproveRequest(BaseModel):
    """POST /tasks/{id}/permission-requests/{rid}/approve"""
    action: str  # "approve" | "reject"
    approved_entries: list[dict] = Field(default_factory=list)
    ttl_seconds: int = 300
    comment: str = ""


class GatewayCallRequest(BaseModel):
    """POST /gateway/call"""
    call_type: str  # "mcp" | "a2a"
    task_id: Optional[str] = None
    # MCP
    tool_name: str = ""
    tool_owner: str = ""
    tool_args: dict = Field(default_factory=dict)
    # A2A
    callee_agent_id: str = ""
    message: dict = Field(default_factory=dict)


# ============================================================
# 响应模型
# ============================================================

class TokenResponse(BaseModel):
    """令牌查询响应"""
    token_id: str
    agent_id: str
    label: str
    entries: list[TokenEntry]
    status: TokenStatus
    created_at: datetime
    revoked_at: Optional[datetime] = None


class CreateTokenResponse(BaseModel):
    token_id: str
    message: str = "Token created."


class EntryResponse(BaseModel):
    entry_id: str
    token_id: str
    effect: TokenEffect
    object_type: ObjectType
    object_id: str
    tool_owner: str


class RevokeResponse(BaseModel):
    token_id: str = ""
    status: str = "revoked"
    message: str


class TaskPermissionResponse(BaseModel):
    entry_id: str
    task_id: str
    agent_id: str
    effect: TokenEffect
    object_type: ObjectType
    object_id: str
    tool_owner: str
    source: PermissionSource
    expires_at: datetime


class PermissionRequestResponse(BaseModel):
    request_id: str
    task_id: str
    agent_id: str
    reason: str
    status: RequestStatus
    requested_entries: list[dict]
    approved_entries: list[dict]
    requested_ttl: int
    approved_ttl: Optional[int]
    reviewed_by: Optional[str]
    review_comment: Optional[str]
    created_at: datetime
    reviewed_at: Optional[datetime]


class GatewayCallResponse(BaseModel):
    """网关调用响应"""
    status: str  # "allowed" | "denied"
    reason: str = ""
    can_request: bool = False
    request_permission_url: str = ""
    missing_entries: list[dict] = Field(default_factory=list)
    message: str = ""
    # 放行时的转发信息
    target_url: str = ""
    session_id: str = ""


class TokenViewResponse(BaseModel):
    view_id: str
    session_id: str
    agent_id: str
    task_id: Optional[str]
    entries: list[TokenEntry]
    built_at: datetime


class FinalizeResponse(BaseModel):
    task_id: str
    sessions_completed: int
    permissions_cleaned: int
    message: str = "Task finalized."
