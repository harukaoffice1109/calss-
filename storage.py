from __future__ import annotations

import json
from datetime import datetime
from typing import Any

APP_VERSION = "0.1.0"


def build_analysis_package(title: str, structure: dict[str, Any], analyzed_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "app": "高考日语课堂小助手",
        "version": APP_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "title": title or structure.get("title") or "高考日语试卷",
        "answer_map": structure.get("answer_map", {}),
        "blocks": analyzed_blocks,
        "raw_structure": structure,
    }


def package_to_bytes(pkg: dict[str, Any]) -> bytes:
    return json.dumps(pkg, ensure_ascii=False, indent=2).encode("utf-8")


def load_package(uploaded_file) -> dict[str, Any]:
    return json.loads(uploaded_file.getvalue().decode("utf-8"))


def block_label(block: dict[str, Any]) -> str:
    qrange = block.get("question_range") or ""
    title = block.get("title") or block.get("block_id") or "题块"
    return f"{title}（{qrange}）" if qrange else str(title)


def question_label(q: dict[str, Any]) -> str:
    number = q.get("number", "?")
    ans = q.get("answer", "")
    return f"第{number}题  答案：{ans}" if ans else f"第{number}题"
