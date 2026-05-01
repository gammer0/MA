"""LLM 客户端 — 调用 DeepSeek / OpenAI 兼容 API"""
import os
import json
import httpx

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


async def chat(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    """调用 LLM 完成对话。"""
    if not LLM_API_KEY:
        return f"[LLM 未配置] {prompt[:50]}..."

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{LLM_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.3,
            },
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        return f"[LLM 错误: {resp.status_code}] {resp.text[:200]}"
