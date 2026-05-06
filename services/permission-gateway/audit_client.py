"""权限网关 - 审计模块 HTTP 客户端（异步 fire-and-forget）"""
import asyncio
import logging
import httpx
from config import AUDIT_SERVICE_URL, SERVICE_API_KEY

logger = logging.getLogger(__name__)


async def _post_async(url: str, body: dict) -> None:
    """异步 POST，fire-and-forget。"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                url,
                json=body,
                headers={"X-Service-API-Key": SERVICE_API_KEY},
            )
    except Exception as exc:
        logger.warning("审计日志发送失败: url=%s, error=%s", url, exc)


def send_signature_record(record: dict) -> None:
    """异步发送签名记录到审计模块。"""
    asyncio.create_task(_post_async(f"{AUDIT_SERVICE_URL}/audit/signature-records", record))


def send_session_log(log: dict) -> None:
    """异步发送会话日志到审计模块。"""
    asyncio.create_task(_post_async(f"{AUDIT_SERVICE_URL}/audit/session-logs", log))


def send_permission_decision(decision: dict) -> None:
    """异步发送权限判定记录到审计模块。"""
    asyncio.create_task(_post_async(f"{AUDIT_SERVICE_URL}/audit/permission-decisions", decision))


def send_task_event(event: dict) -> None:
    """异步发送任务生命周期事件到审计模块。"""
    asyncio.create_task(_post_async(f"{AUDIT_SERVICE_URL}/audit/task-events", event))


def send_permission_request_log(log: dict) -> None:
    """异步发送权限申请审批日志到审计模块。"""
    asyncio.create_task(_post_async(f"{AUDIT_SERVICE_URL}/audit/permission-request-logs", log))
