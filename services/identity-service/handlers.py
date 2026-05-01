"""身份注册服务 - API 路由处理"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncConnection
from redis.asyncio import Redis

from config import DEFAULT_CERT_TTL_DAYS
from crypto import (
    generate_ed25519_keypair,
    build_session_signature_payload,
    verify_signature,
)
from models import (
    RegisterAgentRequest,
    RegisterAgentResponse,
    AgentResponse,
    VerifySignatureRequest,
    VerifySignatureResponse,
    PublicKeyResponse,
    RevokeResponse,
    RenewResponse,
    RegisterToolRequest,
    RegisterToolResponse,
    ToolResponse,
    RevokeToolResponse,
    AgentRecord,
    CertStatus,
    ToolRecord,
    ToolStatus,
)
from cert_store import (
    store_agent_cert,
    get_agent_cert,
    get_agent_by_name_owner,
    list_agent_certs,
    update_agent_status,
    update_agent_key,
    get_agent_public_key,
)
from tool_store import (
    store_tool,
    get_tool,
    list_tools,
    get_tool_by_owner_and_name,
    update_tool_status,
)
from cache import cache_agent_public_key, get_cached_public_key, invalidate_agent_cache

router = APIRouter()


# ============================================================
# 依赖注入：获取数据库连接和 Redis 连接
# ============================================================

from sqlalchemy.ext.asyncio import AsyncConnection as SAC, AsyncEngine

async def get_db(request: Request):
    """从 app.state 获取数据库连接（自动提交）。"""
    engine: AsyncEngine = request.app.state.db_engine
    async with engine.begin() as conn:
        yield conn


async def get_redis(request: Request) -> Redis:
    """从 app.state 获取 Redis 连接。"""
    return request.app.state.redis


# ============================================================
# Agent 管理 API
# ============================================================

@router.post("/agents/register", response_model=RegisterAgentResponse)
async def handle_register(
    request: RegisterAgentRequest,
    conn: AsyncConnection = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    POST /agents/register
    管理员预注册 Agent。若同名同 owner 已存在 active Agent，则复用（更新密钥）。
    1. 检查是否存在同名同 owner 的 active Agent
    2. 若存在：更新密钥对，返回已有 agent_id + 新私钥
    3. 若不存在：生成新密钥对 + 新 agent_id
    注意：private_key 仅在此次响应中返回，服务端不存储！
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=DEFAULT_CERT_TTL_DAYS)

    # 检查是否存在同名同 owner 的 Agent，存在则先吊销再新建
    existing = await get_agent_by_name_owner(conn, request.agent_name, request.owner)
    if existing is not None:
        if existing.status == CertStatus.active:
            await update_agent_status(conn, existing.id, CertStatus.revoked)
            await invalidate_agent_cache(redis, existing.id)

    # 新建
    private_key_pem, public_key_pem = generate_ed25519_keypair()
    agent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=DEFAULT_CERT_TTL_DAYS)

    agent = AgentRecord(
        id=agent_id,
        agent_name=request.agent_name,
        agent_type=request.agent_type,
        public_key=public_key_pem,
        owner=request.owner,
        status=CertStatus.active,
        issued_at=now,
        expires_at=expires_at,
        metadata=request.metadata,
    )

    await store_agent_cert(conn, agent)

    # 计算 Redis TTL（秒）
    ttl_seconds = int((expires_at - now).total_seconds())
    await cache_agent_public_key(redis, agent_id, public_key_pem, ttl_seconds)

    return RegisterAgentResponse(
        agent_id=agent_id,
        agent_name=request.agent_name,
        agent_type=request.agent_type,
        private_key_pem=private_key_pem,
    )


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def handle_get_agent(
    agent_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """
    GET /agents/{agent_id}
    返回 Agent 公开信息（不含私钥）。
    """
    agent = await get_agent_cert(conn, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse(
        agent_id=agent.id,
        agent_name=agent.agent_name,
        agent_type=agent.agent_type,
        public_key=agent.public_key,
        owner=agent.owner,
        status=agent.status,
        issued_at=agent.issued_at,
        expires_at=agent.expires_at,
        revoked_at=agent.revoked_at,
        metadata=agent.metadata,
    )


@router.get("/agents", response_model=list[AgentResponse])
async def handle_list_agents(
    status: Optional[str] = None,
    conn: AsyncConnection = Depends(get_db),
):
    """
    GET /agents
    列出所有 Agent，可按状态过滤。
    """
    agents = await list_agent_certs(conn, status_filter=status)
    return [
        AgentResponse(
            agent_id=a.id,
            agent_name=a.agent_name,
            agent_type=a.agent_type,
            public_key=a.public_key,
            owner=a.owner,
            status=a.status,
            issued_at=a.issued_at,
            expires_at=a.expires_at,
            revoked_at=a.revoked_at,
            metadata=a.metadata,
        )
        for a in agents
    ]


@router.post("/agents/{agent_id}/revoke", response_model=RevokeResponse)
async def handle_revoke(
    agent_id: str,
    conn: AsyncConnection = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    POST /agents/{agent_id}/revoke
    吊销证书（软删除）。
    """
    agent = await get_agent_cert(conn, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status == CertStatus.revoked:
        raise HTTPException(status_code=400, detail="Agent already revoked")

    await update_agent_status(conn, agent_id, CertStatus.revoked)
    await invalidate_agent_cache(redis, agent_id)

    return RevokeResponse(
        agent_id=agent_id,
        status=CertStatus.revoked,
        message="Agent certificate revoked.",
    )


@router.post("/agents/{agent_id}/renew", response_model=RenewResponse)
async def handle_renew(
    agent_id: str,
    conn: AsyncConnection = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    POST /agents/{agent_id}/renew
    续期证书，生成新密钥对。
    """
    agent = await get_agent_cert(conn, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status == CertStatus.revoked:
        raise HTTPException(status_code=400, detail="Cannot renew revoked agent")

    private_key_pem, public_key_pem = generate_ed25519_keypair()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=DEFAULT_CERT_TTL_DAYS)

    await update_agent_key(conn, agent_id, public_key_pem, now, expires_at)

    # 更新 Redis 缓存
    ttl_seconds = int((expires_at - now).total_seconds())
    await invalidate_agent_cache(redis, agent_id)
    await cache_agent_public_key(redis, agent_id, public_key_pem, ttl_seconds)

    return RenewResponse(
        agent_id=agent_id,
        private_key_pem=private_key_pem,
        issued_at=now,
        expires_at=expires_at,
    )


# ============================================================
# 验证 API（供权限网关调用）
# ============================================================

@router.post("/verify/signature", response_model=VerifySignatureResponse)
async def handle_verify_signature(
    request: VerifySignatureRequest,
    conn: AsyncConnection = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    POST /verify/signature
    供权限网关调用，验证会话签名。
    """
    # 1. 获取公钥（优先 Redis）
    public_key_pem = await get_cached_public_key(redis, request.agent_id)

    agent_status = None
    if public_key_pem is None:
        # Redis 未命中，回源 PG
        result = await get_agent_public_key(conn, request.agent_id)
        if result is None:
            return VerifySignatureResponse(
                verified=False,
                agent_id=request.agent_id,
                detail="Agent not found",
            )
        public_key_pem, agent_status = result
    else:
        # 从缓存命中，仍需查状态
        pg_result = await get_agent_public_key(conn, request.agent_id)
        if pg_result is None:
            return VerifySignatureResponse(
                verified=False,
                agent_id=request.agent_id,
                detail="Agent not found",
            )
        _, agent_status = pg_result

    # 2. 检查 Agent 状态
    if agent_status != CertStatus.active:
        return VerifySignatureResponse(
            verified=False,
            agent_id=request.agent_id,
            detail=f"Agent is {agent_status.value}",
        )

    # 3. 构造 payload 并验签
    request_body_bytes = request.request_body.encode("utf-8")
    payload = build_session_signature_payload(
        agent_id=request.agent_id,
        session_id=request.session_id,
        call_id=request.call_id,
        timestamp=request.timestamp,
        request_body=request_body_bytes,
        callee_agent_id=request.callee_agent_id,
        mcp_tool_name=request.mcp_tool_name,
        tool_owner=request.tool_owner,
    )

    verified = verify_signature(payload, request.signature_hex, public_key_pem)

    return VerifySignatureResponse(
        verified=verified,
        agent_id=request.agent_id,
        detail="Signature verified" if verified else "Invalid signature",
    )


@router.get("/agents/{agent_id}/public-key", response_model=PublicKeyResponse)
async def handle_get_public_key(
    agent_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """
    GET /agents/{agent_id}/public-key
    供权限网关/审计模块获取公钥。
    """
    result = await get_agent_public_key(conn, agent_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    public_key_pem, status = result
    return PublicKeyResponse(
        agent_id=agent_id,
        public_key=public_key_pem,
        status=status,
    )


# ============================================================
# MCP 工具注册 API
# ============================================================

@router.post("/tools/register", response_model=RegisterToolResponse)
async def handle_register_tool(
    request: RegisterToolRequest,
    conn: AsyncConnection = Depends(get_db),
):
    """
    POST /tools/register
    注册 MCP 工具。
    """
    # 校验同一 owner 下 tool_name 唯一（active 状态）
    existing = await get_tool_by_owner_and_name(
        conn, request.tool_owner, request.tool_name
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Tool '{request.tool_name}' already exists for owner '{request.tool_owner}'",
        )

    tool_id = str(uuid.uuid4())
    tool = ToolRecord(
        id=tool_id,
        tool_name=request.tool_name,
        tool_owner=request.tool_owner,
        description=request.description,
        tool_schema=request.tool_schema,
        status=ToolStatus.active,
    )

    await store_tool(conn, tool)

    return RegisterToolResponse(
        tool_id=tool_id,
        tool_name=request.tool_name,
        tool_owner=request.tool_owner,
    )


@router.get("/tools/{tool_id}", response_model=ToolResponse)
async def handle_get_tool(
    tool_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """GET /tools/{tool_id}"""
    tool = await get_tool(conn, tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return ToolResponse(
        tool_id=tool.id,
        tool_name=tool.tool_name,
        tool_owner=tool.tool_owner,
        description=tool.description,
        tool_schema=tool.tool_schema,
        status=tool.status,
        registered_at=tool.registered_at,
        revoked_at=tool.revoked_at,
    )


@router.get("/tools", response_model=list[ToolResponse])
async def handle_list_tools(
    owner: Optional[str] = None,
    conn: AsyncConnection = Depends(get_db),
):
    """
    GET /tools?owner=xxx
    按属主过滤，不传则返回全部。
    """
    tools = await list_tools(conn, owner_filter=owner)
    return [
        ToolResponse(
            tool_id=t.id,
            tool_name=t.tool_name,
            tool_owner=t.tool_owner,
            description=t.description,
            tool_schema=t.tool_schema,
            status=t.status,
            registered_at=t.registered_at,
            revoked_at=t.revoked_at,
        )
        for t in tools
    ]


@router.post("/tools/{tool_id}/revoke", response_model=RevokeToolResponse)
async def handle_revoke_tool(
    tool_id: str,
    conn: AsyncConnection = Depends(get_db),
):
    """
    POST /tools/{tool_id}/revoke
    吊销工具（软删除）。
    """
    tool = await get_tool(conn, tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    if tool.status == ToolStatus.revoked:
        raise HTTPException(status_code=400, detail="Tool already revoked")

    await update_tool_status(conn, tool_id, ToolStatus.revoked)

    return RevokeToolResponse(
        tool_id=tool_id,
        status=ToolStatus.revoked,
        message="Tool revoked.",
    )
