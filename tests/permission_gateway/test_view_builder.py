"""权限网关 - view_builder 模块测试"""
import pytest
import sys
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta, timezone

gateway_path = Path(__file__).parent.parent.parent / "services" / "permission-gateway"

def _load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, gateway_path / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# 按依赖顺序加载（models 被 token_manager/task_permissions 依赖）
models_mod = _load_module("models", "models.py")
# token_manager 依赖 models
_ = _load_module("token_manager", "token_manager.py")
# task_permissions 依赖 models
_ = _load_module("task_permissions", "task_permissions.py")
# view_builder 依赖 models + token_manager + task_permissions
view_mod = _load_module("view_builder", "view_builder.py")

TokenEntry = models_mod.TokenEntry
TokenView = models_mod.TokenView
TokenEffect = models_mod.TokenEffect
ObjectType = models_mod.ObjectType
evaluate_view = view_mod.evaluate_view
_match_entry = view_mod._match_entry


# ============================================================
# TokenEntry 匹配测试 (_match_entry)
# ============================================================

class TestMatchEntry:
    """权限条目匹配逻辑测试"""

    def test_mcp_match_exact(self):
        """MCP: 精确匹配 tool_name + tool_owner"""
        entry = TokenEntry(
            effect=TokenEffect.allow,
            object_type=ObjectType.mcp_tool,
            object_id="file_read",
            tool_owner="public",
        )
        assert _match_entry(entry, "mcp", "file_read", "public")
        assert not _match_entry(entry, "mcp", "file_write", "public")
        assert not _match_entry(entry, "mcp", "file_read", "searcher")

    def test_a2a_match(self):
        """A2A: 精确匹配 agent_id"""
        entry = TokenEntry(
            effect=TokenEffect.allow,
            object_type=ObjectType.agent,
            object_id="agent-b",
            tool_owner="",
        )
        assert _match_entry(entry, "a2a", "agent-b", "")
        assert not _match_entry(entry, "a2a", "agent-c", "")

    def test_type_mismatch(self):
        """object_type 不匹配时返回 False"""
        entry = TokenEntry(
            effect=TokenEffect.allow,
            object_type=ObjectType.agent,
            object_id="agent-b",
            tool_owner="",
        )
        # MCP 调用不能匹配 A2A 条目
        assert not _match_entry(entry, "mcp", "agent-b", "")

    def test_tool_owner_exact_no_wildcard(self):
        """tool_owner 必须精确匹配"""
        entry = TokenEntry(
            effect=TokenEffect.allow,
            object_type=ObjectType.mcp_tool,
            object_id="file_read",
            tool_owner="public",
        )
        assert not _match_entry(entry, "mcp", "file_read", "")


# ============================================================
# evaluate_view 测试
# ============================================================

class TestEvaluateView:
    """视图判定逻辑测试"""

    def test_allow_when_entry_matches(self):
        """有匹配 allow 条目 → allowed"""
        view = TokenView(entries=[
            TokenEntry(effect=TokenEffect.allow, object_type=ObjectType.mcp_tool,
                       object_id="file_read", tool_owner="public"),
        ])
        result, matched = evaluate_view(view, "mcp", "file_read", "public")
        assert result == "allowed"
        assert matched is None  # allow 不返回 entry_id

    def test_explicitly_denied(self):
        """有匹配 deny 条目 → explicitly_denied"""
        entry = TokenEntry(
            entry_id="entry-deny-1",
            effect=TokenEffect.deny,
            object_type=ObjectType.mcp_tool,
            object_id="chart_gen",
            tool_owner="analyzer",
        )
        view = TokenView(entries=[entry])
        result, matched = evaluate_view(view, "mcp", "chart_gen", "analyzer")
        assert result == "explicitly_denied"
        assert matched == "entry-deny-1"

    def test_deny_priority_over_allow(self):
        """deny 优先于 allow"""
        view = TokenView(entries=[
            TokenEntry(effect=TokenEffect.deny, object_type=ObjectType.mcp_tool,
                       object_id="chart_gen", tool_owner="analyzer"),
            TokenEntry(effect=TokenEffect.allow, object_type=ObjectType.mcp_tool,
                       object_id="chart_gen", tool_owner="analyzer"),
        ])
        result, _ = evaluate_view(view, "mcp", "chart_gen", "analyzer")
        assert result == "explicitly_denied", \
            "deny 应该优先于 allow"

    def test_permission_required_when_no_match(self):
        """无任何匹配 → permission_required"""
        view = TokenView(entries=[])
        result, _ = evaluate_view(view, "mcp", "nonexistent", "public")
        assert result == "permission_required"

    def test_deny_ordering_matters(self):
        """deny 排在前面时先被检查"""
        # deny 在前
        view = TokenView(entries=[
            TokenEntry(effect=TokenEffect.deny, object_type=ObjectType.mcp_tool,
                       object_id="tool_x", tool_owner="public"),
        ])
        result, _ = evaluate_view(view, "mcp", "tool_x", "public")
        assert result == "explicitly_denied"
