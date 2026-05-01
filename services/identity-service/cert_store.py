"""身份注册服务 - Agent 证书 PostgreSQL 存储层"""
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import text

from models import AgentRecord, CertStatus


async def store_agent_cert(conn: AsyncConnection, agent: AgentRecord) -> None:
    """将 Agent 证书信息写入 PostgreSQL。"""
    await conn.execute(
        text("""
            INSERT INTO agents (id, agent_name, agent_type, public_key, owner,
                               status, issued_at, expires_at, revoked_at, metadata,
                               created_at, updated_at)
            VALUES (:id, :agent_name, :agent_type, :public_key, :owner,
                    :status, :issued_at, :expires_at, :revoked_at, :metadata,
                    :created_at, :updated_at)
        """),
        {
            "id": agent.id,
            "agent_name": agent.agent_name,
            "agent_type": agent.agent_type.value,
            "public_key": agent.public_key,
            "owner": agent.owner,
            "status": agent.status.value,
            "issued_at": agent.issued_at,
            "expires_at": agent.expires_at,
            "revoked_at": agent.revoked_at,
            "metadata": json.dumps(agent.metadata),
            "created_at": agent.created_at,
            "updated_at": agent.updated_at,
        },
    )


async def get_agent_cert(conn: AsyncConnection, agent_id: str) -> Optional[AgentRecord]:
    """从 PostgreSQL 读取 Agent 证书信息。"""
    result = await conn.execute(
        text("SELECT * FROM agents WHERE id = :id"),
        {"id": agent_id},
    )
    row = result.fetchone()
    if row is None:
        return None
    return _row_to_agent_record(row)


async def get_agent_by_name_owner(
    conn: AsyncConnection, agent_name: str, owner: str
) -> Optional[AgentRecord]:
    """按名称和属主查询 active 状态的 Agent（用于去重）。"""
    result = await conn.execute(
        text("SELECT * FROM agents WHERE agent_name = :name AND owner = :owner AND status = 'active'"),
        {"name": agent_name, "owner": owner},
    )
    row = result.fetchone()
    if row is None:
        return None
    return _row_to_agent_record(row)


async def list_agent_certs(
    conn: AsyncConnection, status_filter: Optional[str] = None
) -> list[AgentRecord]:
    """列出所有 Agent，可按状态过滤。"""
    if status_filter:
        result = await conn.execute(
            text("SELECT * FROM agents WHERE status = :status ORDER BY created_at DESC"),
            {"status": status_filter},
        )
    else:
        result = await conn.execute(
            text("SELECT * FROM agents ORDER BY created_at DESC")
        )
    rows = result.fetchall()
    return [_row_to_agent_record(row) for row in rows]


async def update_agent_status(
    conn: AsyncConnection, agent_id: str, status: CertStatus, **extra
) -> None:
    """更新 Agent 状态（revoked/expired）及相关时间戳。"""
    now = datetime.now(timezone.utc)
    set_clauses = ["status = :status", "updated_at = :now"]
    params = {"id": agent_id, "status": status.value, "now": now}

    if status == CertStatus.revoked and "revoked_at" not in extra:
        set_clauses.append("revoked_at = :revoked_at")
        params["revoked_at"] = now

    for key in ("revoked_at", "expires_at"):
        if key in extra:
            set_clauses.append(f"{key} = :{key}")
            params[key] = extra[key]

    sql = f"UPDATE agents SET {', '.join(set_clauses)} WHERE id = :id"
    await conn.execute(text(sql), params)


async def update_agent_key(
    conn: AsyncConnection,
    agent_id: str,
    public_key_pem: str,
    issued_at: datetime,
    expires_at: datetime,
) -> None:
    """续期时更新公钥和有效期。"""
    now = datetime.now(timezone.utc)
    await conn.execute(
        text("""
            UPDATE agents
            SET public_key = :public_key, issued_at = :issued_at,
                expires_at = :expires_at, status = :status,
                revoked_at = NULL, updated_at = :now
            WHERE id = :id
        """),
        {
            "id": agent_id,
            "public_key": public_key_pem,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "status": CertStatus.active.value,
            "now": now,
        },
    )


async def get_agent_public_key(
    conn: AsyncConnection, agent_id: str
) -> Optional[tuple[str, CertStatus]]:
    """获取 Agent 公钥和状态（轻量查询，用于验签）。"""
    result = await conn.execute(
        text("SELECT public_key, status FROM agents WHERE id = :id"),
        {"id": agent_id},
    )
    row = result.fetchone()
    if row is None:
        return None
    return (row.public_key, CertStatus(row.status))


# ============================================================
# 内部辅助函数
# ============================================================

def _row_to_agent_record(row) -> AgentRecord:
    """将数据库行转换为 AgentRecord。"""
    return AgentRecord(
        id=str(row.id),
        agent_name=row.agent_name,
        agent_type=row.agent_type,
        public_key=row.public_key,
        owner=row.owner,
        status=CertStatus(row.status),
        issued_at=row.issued_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        metadata=_parse_json(row.metadata),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _parse_json(val):
    """安全解析 JSON，失败返回空字典。"""
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val) if isinstance(val, str) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
