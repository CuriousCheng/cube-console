"""AI 接口探测：支持 OpenAI 兼容 和 Anthropic 两种协议。"""

from __future__ import annotations

import httpx

OPENCODE_SESSION = "wren-console"


def _anthropic_headers(api_key: str, base: str) -> dict:
    h = {"anthropic-version": "2023-06-01"}
    if api_key:
        h["x-api-key"] = api_key
        h["Authorization"] = f"Bearer {api_key}"
    if "opencode" in base:
        h["x-opencode-session"] = OPENCODE_SESSION
    return h


def _urls(protocol: str, base: str) -> str:
    base = base.rstrip("/")
    if protocol == "anthropic":
        return f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
    return f"{base}/models"


async def probe(protocol: str, base_url: str, api_key: str, timeout: float = 15.0) -> dict:
    """调 /models 看能不能通，顺便把模型列表带回来。"""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return {"ok": False, "error": "未填写接口地址"}

    url = _urls(protocol, base)
    headers = (
        _anthropic_headers(api_key, base)
        if protocol == "anthropic"
        else {"Authorization": f"Bearer {api_key}"} if api_key else {}
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url, headers=headers)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"连不上：{e}"}

    if r.status_code >= 400:
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}

    models: list[str] = []
    raw = r.text[:400]
    try:
        j = r.json()
        if isinstance(j.get("data"), list):
            models = [m.get("id") for m in j["data"] if m.get("id")]
        elif isinstance(j.get("models"), dict):
            models = list(j["models"].keys())
        elif isinstance(j.get("models"), list):
            models = [m.get("id") or m.get("name") for m in j["models"] if m]
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "models": models, "endpoint": url, "raw": raw}


async def chat(
    protocol: str,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int = 1024,
    timeout: float = 90.0,
) -> str:
    """问一次模型，返回纯文本。"""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("还没配置 AI 接口地址")
    if not model:
        raise RuntimeError("还没配置模型名")

    if protocol == "anthropic":
        url = f"{base}/messages" if base.endswith("/v1") else f"{base}/v1/messages"
        headers = _anthropic_headers(api_key, base)
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
    else:
        url = f"{base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body = {
            "model": model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }

    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(url, json=body, headers=headers)

    if r.status_code >= 400:
        raise RuntimeError(f"AI 返回 {r.status_code}: {r.text[:300]}")

    j = r.json()
    if protocol == "anthropic":
        text = "".join(
            b.get("text", "") for b in j.get("content", []) if b.get("type") == "text"
        )
    else:
        text = j.get("choices", [{}])[0].get("message", {}).get("content", "")

    text = (text or "").strip()
    for fence in ("```sql", "```SQL", "```"):
        text = text.replace(fence, "")
    return text.strip().rstrip(";").strip()
