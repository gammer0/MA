"""Agent SDK - 安全Agent基类"""
import uuid
import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx

from .signing_utils import build_session_signature_payload, sign_payload


class PermissionDeniedError(Exception):
    """权限被拒绝异常"""
    def __init__(self, reason: str, can_request: bool = False):
        self.reason = reason
        self.can_request = can_request
        super().__init__(reason)


class SecureAgentClient:
    """
    合规 Agent 的基类。封装与安全内核的全部交互。
    执行层的每个 Agent 都继承此类。
    """

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str):
        self.agent_id = agent_id
        self._private_key = private_key_pem
        self._gateway_url = gateway_url

    # ============================================================
    # 核心调用方法（唯一出站通道）
    # ============================================================

    async def call_agent(
        self,
        callee_agent_id: str,
        message: dict,
        task_id: str,
        parent_session_id: Optional[str] = None,
    ) -> dict:
        """调用另一个 Agent（A2A）。"""
        session_id = str(uuid.uuid4())
        call_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        request_body = {
            "call_type": "a2a",
            "task_id": task_id,
            "tool_name": "",
            "tool_owner": "",
            "tool_args": {},
            "callee_agent_id": callee_agent_id,
            "message": message,
        }
        return await self._make_call(session_id, call_id, timestamp, request_body, parent_session_id)

    async def call_mcp_tool(
        self,
        tool_name: str,
        tool_owner: str,
        tool_args: dict,
        task_id: str,
        parent_session_id: Optional[str] = None,
    ) -> dict:
        """调用 MCP 工具。"""
        session_id = str(uuid.uuid4())
        call_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        request_body = {
            "call_type": "mcp",
            "task_id": task_id,
            "tool_name": tool_name,
            "tool_owner": tool_owner,
            "tool_args": tool_args,
            "callee_agent_id": "",
            "message": {},
        }
        return await self._make_call(session_id, call_id, timestamp, request_body, parent_session_id)

    async def _make_call(
        self, session_id: str, call_id: str, timestamp: str, body: dict,
        parent_session_id: Optional[str] = None,
    ) -> dict:
        """内部：签名并调网关。"""
        # 透传 parent_session_id 到请求体
        if parent_session_id:
            body["parent_session_id"] = parent_session_id

        body_json = json.dumps(body)
        body_bytes = body_json.encode("utf-8")

        # 构造 payload 并签名
        payload = build_session_signature_payload(
            agent_id=self.agent_id,
            session_id=session_id,
            call_id=call_id,
            timestamp=timestamp,
            request_body=body_bytes,
            callee_agent_id=body.get("callee_agent_id", ""),
            mcp_tool_name=body.get("tool_name", ""),
            tool_owner=body.get("tool_owner", ""),
        )
        signature_hex = sign_payload(payload, self._private_key)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._gateway_url}/gateway/call",
                json=body,
                headers={
                    "X-Agent-Id": self.agent_id,
                    "X-Session-Id": session_id,
                    "X-Call-Id": call_id,
                    "X-Signature-Hex": signature_hex,
                    "X-Timestamp": timestamp,
                },
            )
            data = response.json()

            if response.status_code == 200 and data.get("status") == "allowed":
                return data

            # 403 处理
            if data.get("can_request", False):
                # 自动发起权限申请
                task_id = body.get("task_id", "")
                req_id = await self.request_permission(
                    task_id=task_id,
                    reason=f"Agent {self.agent_id} 需要权限 {data.get('missing_entries', [])}",
                    missing_entries=data.get("missing_entries", []),
                )
                # 等待审批
                approved = await self.wait_for_approval(task_id, req_id)
                if approved:
                    # 重试
                    return await self._make_call(session_id, call_id, timestamp, body)
                raise PermissionDeniedError("Permission request was rejected.", can_request=True)

            raise PermissionDeniedError(
                data.get("message", "Access denied."),
                can_request=data.get("can_request", False),
            )

    # ============================================================
    # 权限申请
    # ============================================================

    async def request_permission(
        self,
        task_id: str,
        reason: str,
        missing_entries: list,
        ttl: int = 600,
    ) -> str:
        """发起权限申请。返回 request_id。"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self._gateway_url}/tasks/{task_id}/permission-requests",
                json={
                    "agent_id": self.agent_id,
                    "reason": reason,
                    "requested_entries": missing_entries,
                    "ttl_seconds": ttl,
                },
            )
            data = response.json()
            return data.get("request_id", "")

    async def wait_for_approval(
        self,
        task_id: str,
        request_id: str,
        poll_interval: int = 3,
        timeout: int = 120,
    ) -> bool:
        """轮询等待审批结果。"""
        deadline = time.time() + timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.time() < deadline:
                try:
                    response = await client.get(
                        f"{self._gateway_url}/tasks/{task_id}/permission-requests/{request_id}",
                    )
                    data = response.json()
                    status = data.get("status", "")
                    if status == "approved":
                        return True
                    if status == "rejected":
                        return False
                except Exception:
                    pass
                await asyncio.sleep(poll_interval)
        return False

    # ============================================================
    # 任务生命周期
    # ============================================================

    async def finalize_task(self, task_id: str) -> None:
        """通知网关任务结束，触发级联清理。"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{self._gateway_url}/tasks/{task_id}/finalize")
