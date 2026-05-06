"""LLM 客户端 — 调用 DeepSeek / OpenAI 兼容 API"""
import os
import json
import httpx

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
_raw_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
# 清洗：去掉 # 注释、空格、以及非模型名的后缀（如中文注释等）
LLM_MODEL = _raw_model.split("#")[0].strip()
if LLM_MODEL and not all(c.isascii() for c in LLM_MODEL):
    # 模型名不应含非 ASCII 字符，提取纯 ASCII 前缀
    LLM_MODEL = "".join(c for c in LLM_MODEL if c.isascii()).strip()


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
