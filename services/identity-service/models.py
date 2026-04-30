"""身份注册服务 - Pydantic 数据模型"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 枚举
# ============================================================

class AgentType(str, Enum):
    orchestrator = "orchestrator"
    worker = "worker"
    tool_proxy = "tool-proxy"


class CertStatus(str, Enum):
    active = "active"
    revoked = "revoked"
    expired = "expired"


class ToolStatus(str, Enum):
    active = "active"
    revoked = "revoked"


# ============================================================
# Agent 数据模型
# ============================================================

class AgentRecord(BaseModel):
    """Agent 证书记录（数据库模型）"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str
    agent_type: AgentType
    public_key: str  # PEM 格式
    owner: str
    status: CertStatus = CertStatus.active
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# 请求模型
# ============================================================

class RegisterAgentRequest(BaseModel):
    """POST /agents/register"""
    agent_name: str
    agent_type: AgentType
    owner: str
    metadata: dict = Field(default_factory=dict)


class VerifySignatureRequest(BaseModel):
    """POST /verify/signature"""
    agent_id: str
    session_id: str
    call_id: str
    timestamp: str
    request_body: str  # base64 or raw, 由调用方决定
    signature_hex: str
    callee_agent_id: str = ""
    mcp_tool_name: str = ""
    tool_owner: str = ""


class RegisterToolRequest(BaseModel):
    """POST /tools/register"""
    tool_name: str
    tool_owner: str  # "public" 或 agent_id
    description: str = ""
    tool_schema: dict = Field(default_factory=dict)


# ============================================================
# 响应模型
# ============================================================

class RegisterAgentResponse(BaseModel):
    """Agent 注册响应"""
    agent_id: str
    agent_name: str
    agent_type: AgentType
    private_key_pem: str  # 仅此响应中返回
    message: str = "Agent registered successfully. Store the private key securely."


class AgentResponse(BaseModel):
    """Agent 查询响应（不含私钥）"""
    agent_id: str
    agent_name: str
    agent_type: AgentType
    public_key: str
    owner: str
    status: CertStatus
    issued_at: datetime
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    metadata: dict


class VerifySignatureResponse(BaseModel):
    """签名验证响应"""
    verified: bool
    agent_id: str
    detail: str = ""


class PublicKeyResponse(BaseModel):
    """公钥查询响应"""
    agent_id: str
    public_key: str
    status: CertStatus


class RevokeResponse(BaseModel):
    """吊销响应"""
    agent_id: str
    status: CertStatus
    message: str


class RenewResponse(BaseModel):
    """续期响应"""
    agent_id: str
    private_key_pem: str
    issued_at: datetime
    expires_at: datetime
    message: str = "Certificate renewed successfully."


class RegisterToolResponse(BaseModel):
    """工具注册响应"""
    tool_id: str
    tool_name: str
    tool_owner: str
    message: str = "Tool registered successfully."


class ToolResponse(BaseModel):
    """工具查询响应"""
    tool_id: str
    tool_name: str
    tool_owner: str
    description: str
    tool_schema: dict
    status: ToolStatus
    registered_at: datetime
    revoked_at: Optional[datetime] = None


class RevokeToolResponse(BaseModel):
    """工具吊销响应"""
    tool_id: str
    status: ToolStatus
    message: str


# ============================================================
# MCP 工具数据模型
# ============================================================

class ToolRecord(BaseModel):
    """MCP 工具记录（数据库模型）"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    tool_owner: str  # "public" 或 agent_id
    description: str = ""
    tool_schema: dict = Field(default_factory=dict)
    status: ToolStatus = ToolStatus.active
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revoked_at: Optional[datetime] = None
