from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st


class AIClientError(RuntimeError):
    pass


def get_secret(name: str, default: str | None = None) -> str | None:
    try:
        value = st.secrets.get(name)  # type: ignore[attr-defined]
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


def get_config() -> dict[str, str]:
    api_key = get_secret("OPENAI_API_KEY")
    base_url = get_secret("OPENAI_BASE_URL", "https://tokenflux.dev/v1")
    model = get_secret("OPENAI_MODEL", "gpt-5.4")
    if not api_key:
        raise AIClientError("缺少 OPENAI_API_KEY。请在 Streamlit secrets 或环境变量中设置。")
    return {"api_key": api_key, "base_url": base_url.rstrip("/"), "model": model}


def call_ai(system_prompt: str, user_prompt: str, *, temperature: float = 0.2) -> str:
    """Call an OpenAI-compatible Responses API first, then fall back to Chat Completions."""
    cfg = get_config()
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }

    responses_payload: dict[str, Any] = {
        "model": cfg["model"],
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    try:
        r = requests.post(
            f"{cfg['base_url']}/responses",
            headers=headers,
            json=responses_payload,
            timeout=180,
        )
        if r.status_code < 400:
            data = r.json()
            text = _extract_responses_text(data)
            if text:
                return text
    except requests.RequestException:
        pass

    chat_payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    r = requests.post(
        f"{cfg['base_url']}/chat/completions",
        headers=headers,
        json=chat_payload,
        timeout=180,
    )
    if r.status_code >= 400:
        raise AIClientError(f"API 请求失败：{r.status_code} {r.text[:500]}")
    data = r.json()
    return data["choices"][0]["message"]["content"]


def _extract_responses_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    chunks: list[str] = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()
