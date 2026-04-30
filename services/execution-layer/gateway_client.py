"""执行层 - 权限网关 HTTP 客户端"""
import httpx


async def gateway_call(gateway_url: str, signed_request: dict) -> dict:
    """调用 POST /gateway/call，处理返回。"""
    headers = signed_request.pop("_headers", {})
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{gateway_url}/gateway/call",
            json=signed_request,
            headers=headers,
        )
        return response.json()


async def create_permission_request(gateway_url: str, task_id: str, request: dict) -> str:
    """发起权限申请。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{gateway_url}/tasks/{task_id}/permission-requests",
            json=request,
        )
        return response.json().get("request_id", "")


async def check_approval_status(gateway_url: str, task_id: str, request_id: str) -> str:
    """查询审批状态。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{gateway_url}/tasks/{task_id}/permission-requests/{request_id}",
        )
        return response.json().get("status", "")


async def finalize_task(gateway_url: str, task_id: str) -> None:
    """触发任务结束清理。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(f"{gateway_url}/tasks/{task_id}/finalize")
