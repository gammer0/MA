"""权限网关 - 令牌视图构建器"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncConnection

from models import TokenView, TokenEntry, TokenEffect, ObjectType, CallType
from token_manager import get_agent_standard_tokens
from task_permissions import get_task_permissions


async def build_agent_view(
    conn: AsyncConnection, agent_id: str, task_id: Optional[str] = None
) -> TokenView:
    """
    构建单 Agent 的权限视图（并集）。
    = StandardToken(agent_id).entries ∪ TaskPermissionEntry(task_id, agent_id, valid)

    deny 条目排在前面（优先匹配）。
    """
    entries: list[TokenEntry] = []

    # 1. Agent 的长期令牌条目（active 状态的）
    standard_tokens = await get_agent_standard_tokens(conn, agent_id)
    for token in standard_tokens:
        entries.extend(token.entries)

    # 2. 任务中该 Agent 的临时权限条目（有效期内）
    if task_id:
        task_entries = await get_task_permissions(conn, task_id, agent_id)
        now = datetime.now(timezone.utc)
        for e in task_entries:
            if e.expires_at > now:
                # 转换为 TokenEntry 格式
                entries.append(TokenEntry(
                    entry_id=e.entry_id,
                    token_id="",
                    effect=e.effect,
                    object_type=e.object_type,
                    object_id=e.object_id,
                    tool_owner=e.tool_owner,
                    created_at=e.created_at,
                ))

    # deny 优先排序
    entries.sort(key=lambda e: 0 if e.effect == TokenEffect.deny else 1)

    return TokenView(
        agent_id=agent_id,
        task_id=task_id,
        entries=entries,
    )


async def build_multi_agent_view(
    conn: AsyncConnection,
    caller_id: str,
    callee_id: str,
    task_id: Optional[str] = None,
) -> TokenView:
    """
    构建多 Agent 调用视图（交集 + deny 优先）。

    交集逻辑：
    - allow 条目：取双方都允许的（取交集）
    - deny 条目：任一方的 deny 直接加入最终视图（deny 优先）
    """
    caller_view = await build_agent_view(conn, caller_id, task_id)
    callee_view = await build_agent_view(conn, callee_id, task_id)

    # 收集双方的 deny 条目（任一方的 deny 都生效）
    final_deny: list[TokenEntry] = []
    seen_deny = set()
    for e in caller_view.entries:
        if e.effect == TokenEffect.deny:
            key = (e.object_type.value, e.object_id, e.tool_owner)
            if key not in seen_deny:
                seen_deny.add(key)
                final_deny.append(e)
    for e in callee_view.entries:
        if e.effect == TokenEffect.deny:
            key = (e.object_type.value, e.object_id, e.tool_owner)
            if key not in seen_deny:
                seen_deny.add(key)
                final_deny.append(e)

    # allow 条目取交集（支持通配符 "*"）
    caller_allow = set()
    for e in caller_view.entries:
        if e.effect == TokenEffect.allow:
            caller_allow.add((e.object_type.value, e.object_id, e.tool_owner))

    callee_allow = set()
    for e in callee_view.entries:
        if e.effect == TokenEffect.allow:
            callee_allow.add((e.object_type.value, e.object_id, e.tool_owner))

    intersection = set()
    for ct, ci, co in caller_allow:
        for ct2, ci2, co2 in callee_allow:
            if ct != ct2:
                continue
            if co != co2:
                continue
            # object_id 匹配（包括通配符）
            if ci == "*" or ci2 == "*" or ci == ci2:
                # 取具体的那个
                resolved_id = ci2 if ci == "*" else ci
                intersection.add((ct, resolved_id, co))
                break

    final_entries = list(final_deny)
    for obj_type, obj_id, tool_owner in intersection:
        final_entries.append(TokenEntry(
            effect=TokenEffect.allow,
            object_type=ObjectType(obj_type),
            object_id=obj_id,
            tool_owner=tool_owner,
        ))

    return TokenView(
        entries=final_entries,
    )


def evaluate_view(
    view: TokenView, call_type: str, object_id: str, tool_owner: str
) -> tuple[str, Optional[str]]:
    """
    判定：遍历视图条目，先 deny 后 allow。
    Returns:
        ("allowed", None)
        ("explicitly_denied", entry_id)
        ("permission_required", None)
    """
    for entry in view.entries:
        if not _match_entry(entry, call_type, object_id, tool_owner):
            continue
        if entry.effect == TokenEffect.deny:
            return ("explicitly_denied", entry.entry_id)
        if entry.effect == TokenEffect.allow:
            return ("allowed", None)

    return ("permission_required", None)


def _match_entry(
    entry: TokenEntry, call_type: str, object_id: str, tool_owner: str
) -> bool:
    """判断一条权限条目是否匹配当前调用"""
    expected_type = "agent" if call_type == "a2a" else "mcp_tool"
    if entry.object_type.value != expected_type:
        return False
    if entry.object_id != "*" and entry.object_id != object_id:
        return False
    if call_type == "mcp":
        if entry.tool_owner != tool_owner:
            return False
    return True
