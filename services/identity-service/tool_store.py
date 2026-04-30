"""身份注册服务 - MCP 工具 PostgreSQL 存储层"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import text

from models import ToolRecord, ToolStatus


async def store_tool(conn: AsyncConnection, tool: ToolRecord) -> None:
    """将 MCP 工具信息写入 PostgreSQL。"""
    await conn.execute(
        text("""
            INSERT INTO mcp_tools (id, tool_name, tool_owner, description,
                                   tool_schema, status, registered_at, revoked_at)
            VALUES (:id, :tool_name, :tool_owner, :description,
                    :tool_schema, :status, :registered_at, :revoked_at)
        """),
        {
            "id": tool.id,
            "tool_name": tool.tool_name,
            "tool_owner": tool.tool_owner,
            "description": tool.description,
            "tool_schema": tool.tool_schema,
            "status": tool.status.value,
            "registered_at": tool.registered_at,
            "revoked_at": tool.revoked_at,
        },
    )


async def get_tool(conn: AsyncConnection, tool_id: str) -> Optional[ToolRecord]:
    """按 ID 查询工具。"""
    result = await conn.execute(
        text("SELECT * FROM mcp_tools WHERE id = :id"),
        {"id": tool_id},
    )
    row = result.fetchone()
    if row is None:
        return None
    return _row_to_tool_record(row)


async def list_tools(
    conn: AsyncConnection, owner_filter: Optional[str] = None
) -> list[ToolRecord]:
    """列出工具，可按 owner 过滤（public / agent_id）。"""
    if owner_filter:
        result = await conn.execute(
            text(
                "SELECT * FROM mcp_tools WHERE tool_owner = :owner "
                "ORDER BY registered_at DESC"
            ),
            {"owner": owner_filter},
        )
    else:
        result = await conn.execute(
            text("SELECT * FROM mcp_tools ORDER BY registered_at DESC")
        )
    rows = result.fetchall()
    return [_row_to_tool_record(row) for row in rows]


async def get_tool_by_owner_and_name(
    conn: AsyncConnection, tool_owner: str, tool_name: str
) -> Optional[ToolRecord]:
    """按属主和名称查询 active 工具（用于唯一性校验）。"""
    result = await conn.execute(
        text(
            "SELECT * FROM mcp_tools "
            "WHERE tool_owner = :owner AND tool_name = :name AND status = 'active'"
        ),
        {"owner": tool_owner, "name": tool_name},
    )
    row = result.fetchone()
    if row is None:
        return None
    return _row_to_tool_record(row)


async def update_tool_status(
    conn: AsyncConnection,
    tool_id: str,
    status: ToolStatus,
    revoked_at: Optional[datetime] = None,
) -> None:
    """吊销工具（软删除，标记 revoked）。"""
    if revoked_at is None and status == ToolStatus.revoked:
        revoked_at = datetime.now(timezone.utc)
    await conn.execute(
        text(
            "UPDATE mcp_tools SET status = :status, revoked_at = :revoked_at "
            "WHERE id = :id"
        ),
        {"id": tool_id, "status": status.value, "revoked_at": revoked_at},
    )


# ============================================================
# 内部辅助函数
# ============================================================

def _row_to_tool_record(row) -> ToolRecord:
    """将数据库行转换为 ToolRecord。"""
    return ToolRecord(
        id=str(row.id),
        tool_name=row.tool_name,
        tool_owner=row.tool_owner,
        description=row.description or "",
        tool_schema=row.tool_schema or {},
        status=ToolStatus(row.status),
        registered_at=row.registered_at,
        revoked_at=row.revoked_at,
    )
