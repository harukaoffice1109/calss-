from __future__ import annotations

import base64
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
    return call_ai_messages(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )


def call_ai_vision(system_prompt: str, user_text: str, image_bytes_list: list[bytes], *, temperature: float = 0.1) -> str:
    content: list[dict[str, Any]] = [{"type": "input_text", "text": user_text}]
    for raw in image_bytes_list:
        b64 = base64.b64encode(raw).decode("ascii")
        content.append({"type": "input_image", "image_url": f"data:image/png;base64,{b64}"})
    return call_ai_messages(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        temperature=temperature,
    )


def call_ai_messages(messages: list[dict[str, Any]], *, temperature: float = 0.2) -> str:
    """Call an OpenAI-compatible Responses API first, then fall back to Chat Completions."""
    cfg = get_config()
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }

    responses_payload: dict[str, Any] = {
        "model": cfg["model"],
        "input": messages,
        "temperature": temperature,
    }
    response_error = ""
    try:
        r = requests.post(
            f"{cfg['base_url']}/responses",
            headers=headers,
            json=responses_payload,
            timeout=300,
        )
        if r.status_code < 400:
            data = r.json()
            text = _extract_responses_text(data)
            if text:
                return text
            response_error = "Responses API 返回为空文本"
        else:
            response_error = f"Responses API {r.status_code}: {r.text[:500]}"
    except requests.RequestException as exc:
        response_error = f"Responses API 请求异常：{exc}"

    chat_messages = [_to_chat_message(m) for m in messages]
    chat_payload = {
        "model": cfg["model"],
        "messages": chat_messages,
        "temperature": temperature,
    }
    r = requests.post(
        f"{cfg['base_url']}/chat/completions",
        headers=headers,
        json=chat_payload,
        timeout=300,
    )
    if r.status_code >= 400:
        raise AIClientError(f"API 请求失败：{response_error}；Chat API {r.status_code}: {r.text[:500]}")
    data = r.json()
    return data["choices"][0]["message"]["content"]


def _to_chat_message(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if isinstance(content, list):
        converted = []
        for part in content:
            if part.get("type") == "input_text":
                converted.append({"type": "text", "text": part.get("text", "")})
            elif part.get("type") == "input_image":
                converted.append({"type": "image_url", "image_url": {"url": part.get("image_url", "")}})
        return {"role": message.get("role", "user"), "content": converted}
    return message


def _extract_responses_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    chunks: list[str] = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()
