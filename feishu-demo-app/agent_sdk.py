"""飞书 Demo App — Agent SDK 基类"""
import uuid
import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx


class PermissionDeniedError(Exception):
    """权限被拒绝异常"""
    pass


class SecureAgentClient:
    """合规 Agent 基类。复用 demo-app 的 SDK 核心逻辑。"""

    def __init__(self, agent_id: str, private_key_pem: str, gateway_url: str):
        self.agent_id = agent_id
        self._private_key = private_key_pem
        self._gateway_url = gateway_url

    async def call_agent(self, callee_agent_id: str, message: dict, task_id: str,
                         reason: str = "") -> dict:
        """A2A 调用。"""
        session_id = str(uuid.uuid4())
        call_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        body = {
            "call_type": "a2a", "task_id": task_id,
            "tool_name": "", "tool_owner": "", "tool_args": {},
            "callee_agent_id": callee_agent_id, "message": message,
            "reason": reason,
        }
        return await self._make_call(session_id, call_id, timestamp, body)

    async def call_mcp_tool(self, tool_name: str, tool_owner: str, tool_args: dict,
                            task_id: str, reason: str = "") -> dict:
        """MCP 调用。"""
        session_id = str(uuid.uuid4())
        call_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        body = {
            "call_type": "mcp", "task_id": task_id,
            "tool_name": tool_name, "tool_owner": tool_owner,
            "tool_args": tool_args, "callee_agent_id": "", "message": {},
            "reason": reason,
        }
        return await self._make_call(session_id, call_id, timestamp, body)

    async def _make_call(self, session_id: str, call_id: str, timestamp: str,
                         body: dict) -> dict:
        """签名并调网关。"""
        from signing_utils import build_session_signature_payload, sign_payload

        body_json = json.dumps(body, sort_keys=True, ensure_ascii=False)
        body_bytes = body_json.encode("utf-8")
        payload = build_session_signature_payload(
            agent_id=self.agent_id, session_id=session_id, call_id=call_id,
            timestamp=timestamp, request_body=body_bytes,
            callee_agent_id=body.get("callee_agent_id", ""),
            mcp_tool_name=body.get("tool_name", ""),
            tool_owner=body.get("tool_owner", ""),
        )
        signature_hex = sign_payload(payload, self._private_key)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._gateway_url}/gateway/call", json=body,
                headers={
                    "X-Agent-Id": self.agent_id, "X-Session-Id": session_id,
                    "X-Call-Id": call_id, "X-Signature-Hex": signature_hex,
                    "X-Timestamp": timestamp,
                },
            )
            data = response.json()

            if response.status_code == 200 and data.get("status") == "allowed":
                return data

            if data.get("can_request", False):
                task_id = body.get("task_id", "")
                reason_text = body.get("reason", "") or data.get("reason", "")
                req_id = await self._request_permission(task_id, reason_text, data.get("missing_entries", []))
                approved = await self._wait_approval(task_id, req_id)
                if approved:
                    return await self._make_call(str(uuid.uuid4()), str(uuid.uuid4()), timestamp, body)
                raise PermissionDeniedError("权限申请被拒绝")

            raise PermissionDeniedError(data.get("message", "Access denied."))

    async def _request_permission(self, task_id: str, reason: str, entries: list) -> str:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._gateway_url}/tasks/{task_id}/permission-requests",
                json={"agent_id": self.agent_id, "reason": reason,
                      "requested_entries": entries, "ttl_seconds": 600},
            )
            return resp.json().get("request_id", "")

    async def _wait_approval(self, task_id: str, request_id: str) -> bool:
        deadline = time.time() + 120
        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.time() < deadline:
                resp = await client.get(
                    f"{self._gateway_url}/tasks/{task_id}/permission-requests/{request_id}")
                status = resp.json().get("status", "")
                if status == "approved":
                    return True
                if status == "rejected":
                    return False
                await asyncio.sleep(3)
        return False

    async def finalize_task(self, task_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{self._gateway_url}/tasks/{task_id}/finalize")
