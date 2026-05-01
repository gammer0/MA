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
    构建 A2A 多 Agent 调用视图。

    = caller令牌视图 ∩ callee长期令牌(StandardToken) ∪ callee任务临时权限

    交集规则（按 (type, object_id, tool_owner) 逐对）:
      caller条目 | callee条目 | 结果
      deny       | *          | deny   (任一方 deny 即 deny)
      allow      | deny       | deny
      allow      | unset      | 不构建 (隐式拒绝, 需申请)
      allow      | allow      | allow
      unset      | *          | 不构建 (隐式拒绝)

    特殊: callee 默认具有 allow agent: callee_id (允许被调用)
    """
    caller_view = await build_agent_view(conn, caller_id, task_id)
    callee_standard = await _build_standard_only_view(conn, callee_id)

    # callee 任务临时权限 (不进交集, 直接追加)
    callee_task: list[TokenEntry] = []
    if task_id:
        task_entries = await get_task_permissions(conn, task_id, callee_id)
        now = datetime.now(timezone.utc)
        for e in task_entries:
            if e.expires_at > now:
                callee_task.append(TokenEntry(
                    entry_id=e.entry_id, token_id="",
                    effect=e.effect, object_type=e.object_type,
                    object_id=e.object_id, tool_owner=e.tool_owner,
                    created_at=e.created_at,
                ))

    # 索引: {(type, object_id, tool_owner): effect}
    def _index(view: TokenView) -> dict:
        idx: dict = {}
        for e in view.entries:
            key = (e.object_type.value, e.object_id, e.tool_owner)
            if key not in idx or e.effect == TokenEffect.deny:
                idx[key] = e.effect
        return idx

    caller_idx = _index(caller_view)
    callee_idx = _index(callee_standard)

    # callee 默认允许自己被调用: 隐式 allow agent: callee_id
    callee_self_key = ("agent", callee_id, "")
    if callee_self_key not in callee_idx:
        callee_idx[callee_self_key] = TokenEffect.allow

    final_deny: list[TokenEntry] = []
    final_allow: list[TokenEntry] = []
    seen = set()
    all_keys = set(caller_idx.keys()) | set(callee_idx.keys())

    for obj_type, obj_id, tool_owner in all_keys:
        key = (obj_type, obj_id, tool_owner)
        if key in seen:
            continue
        ce = caller_idx.get(key)      # None = unset
        ca = callee_idx.get(key)      # None = unset

        if ce == TokenEffect.deny or ca == TokenEffect.deny:
            seen.add(key)
            final_deny.append(TokenEntry(
                effect=TokenEffect.deny, object_type=ObjectType(obj_type),
                object_id=obj_id, tool_owner=tool_owner))
        elif ce == TokenEffect.allow and ca == TokenEffect.allow:
            seen.add(key)
            final_allow.append(TokenEntry(
                effect=TokenEffect.allow, object_type=ObjectType(obj_type),
                object_id=obj_id, tool_owner=tool_owner))
        # else: unset/* 或 allow/unset → 隐式拒绝, 不构建条目

    # deny 优先 → allow 交集 → callee 任务临时权限
    return TokenView(entries=list(final_deny) + final_allow + callee_task)


async def _build_standard_only_view(
    conn: AsyncConnection, agent_id: str
) -> TokenView:
    """构建仅含 StandardToken（长期令牌）的视图，不含任务临时权限。"""
    entries: list[TokenEntry] = []
    for token in await get_agent_standard_tokens(conn, agent_id):
        entries.extend(token.entries)
    entries.sort(key=lambda e: 0 if e.effect == TokenEffect.deny else 1)
    return TokenView(agent_id=agent_id, entries=entries)


async def check_temp_permission_denied(
    conn: AsyncConnection,
    agent_id: str,
    task_id: str,
    requested_entries: list[dict],
) -> Optional[str]:
    """
    检查申请的临时权限条目是否被 deny 覆盖。
    返回被 deny 阻止的条目描述（第一个），若全部通过返回 None。

    检查来源：agent 的长期令牌 + 已有任务临时权限。
    """
    view = await build_agent_view(conn, agent_id, task_id)
    for e_dict in requested_entries:
        obj_type = e_dict.get("object_type", "mcp_tool")
        obj_id = e_dict.get("object_id", "")
        tool_owner = e_dict.get("tool_owner", "")
        call_type = "a2a" if obj_type == "agent" else "mcp"
        decision, _ = evaluate_view(view, call_type, obj_id, tool_owner)
        if decision == "explicitly_denied":
            return f"{obj_type}:{obj_id}" + (f"({tool_owner})" if tool_owner else "")
    return None


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
    if entry.object_id != object_id:
        return False
    if call_type == "mcp":
        if entry.tool_owner != tool_owner:
            return False
    return True
