"""审计模块 - trace_builder 调用链组装逻辑测试（不依赖DB）"""
import pytest
import sys
import importlib.util
from pathlib import Path

audit_path = Path(__file__).parent.parent.parent / "services" / "audit-service"

spec = importlib.util.spec_from_file_location("audit_models", audit_path / "models.py")
models_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models_mod)

TraceNode = models_mod.TraceNode


class TestTraceNodeTreeAssembly:
    """TraceNode 树形结构组装测试"""

    def _build_tree(self, sessions: list[dict]) -> list[TraceNode]:
        """
        模拟 trace_builder 的核心逻辑：将平铺 session 组装为树。
        不依赖数据库。
        """
        nodes: dict[str, TraceNode] = {}
        for s in sessions:
            nodes[s["session_id"]] = TraceNode(
                session_id=s["session_id"],
                call_type=s.get("call_type", "a2a"),
                caller_agent_id=s.get("caller_agent_id", ""),
                target_id=s.get("target_id", ""),
                tool_owner=s.get("tool_owner", ""),
                depth=s.get("depth", 0),
                decision=s.get("decision", "allowed"),
                created_at=s.get("created_at", ""),
            )

        roots = []
        for sid, node in nodes.items():
            parent = sessions_dict.get(sid, {}).get("parent_session_id")
            if parent and parent in nodes:
                nodes[parent].children.append(node)
            else:
                roots.append(node)

        return roots

    def test_single_root_session(self):
        """单次调用的树——一个根节点，无子节点"""
        sessions = [
            {"session_id": "s-001", "parent_session_id": None,
             "call_type": "a2a", "caller_agent_id": "orch",
             "target_id": "searcher", "depth": 0, "decision": "allowed"}
        ]
        global sessions_dict
        sessions_dict = {s["session_id"]: s for s in sessions}
        roots = self._build_tree(sessions)

        assert len(roots) == 1
        assert roots[0].session_id == "s-001"
        assert roots[0].children == []

    def test_two_level_tree(self):
        """两层调用——1 个根 + 2 个子节点"""
        sessions = [
            {"session_id": "s-001", "parent_session_id": None,
             "call_type": "a2a", "caller_agent_id": "orch",
             "target_id": "searcher", "depth": 0},
            {"session_id": "s-002", "parent_session_id": "s-001",
             "call_type": "mcp", "caller_agent_id": "searcher",
             "target_id": "web_search", "depth": 1},
            {"session_id": "s-003", "parent_session_id": "s-001",
             "call_type": "mcp", "caller_agent_id": "searcher",
             "target_id": "page_fetch", "depth": 1},
        ]
        global sessions_dict
        sessions_dict = {s["session_id"]: s for s in sessions}
        roots = self._build_tree(sessions)

        assert len(roots) == 1
        assert roots[0].session_id == "s-001"
        assert len(roots[0].children) == 2
        child_ids = {c.session_id for c in roots[0].children}
        assert child_ids == {"s-002", "s-003"}

    def test_three_level_deep_tree(self):
        """三层深调用——agent→agent→tool"""
        sessions = [
            {"session_id": "s-001", "parent_session_id": None,
             "call_type": "a2a", "caller_agent_id": "orch",
             "target_id": "analyzer", "depth": 0},
            {"session_id": "s-007", "parent_session_id": "s-001",
             "call_type": "a2a", "caller_agent_id": "analyzer",
             "target_id": "searcher", "depth": 1},
            {"session_id": "s-008", "parent_session_id": "s-007",
             "call_type": "mcp", "caller_agent_id": "searcher",
             "target_id": "web_search", "depth": 2},
        ]
        global sessions_dict
        sessions_dict = {s["session_id"]: s for s in sessions}
        roots = self._build_tree(sessions)

        assert len(roots) == 1
        assert len(roots[0].children) == 1
        assert roots[0].children[0].session_id == "s-007"
        assert len(roots[0].children[0].children) == 1
        assert roots[0].children[0].children[0].session_id == "s-008"

    def test_multiple_root_sessions(self):
        """多个顶层调用——多个根节点"""
        sessions = [
            {"session_id": "s-001", "parent_session_id": None,
             "call_type": "a2a", "depth": 0},
            {"session_id": "s-004", "parent_session_id": None,
             "call_type": "a2a", "depth": 0},
            {"session_id": "s-010", "parent_session_id": None,
             "call_type": "mcp", "depth": 0},
        ]
        global sessions_dict
        sessions_dict = {s["session_id"]: s for s in sessions}
        roots = self._build_tree(sessions)

        assert len(roots) == 3
