from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

import fitz  # PyMuPDF


@dataclass
class ExtractedPdf:
    filename: str
    text: str
    pages: list[str]


def extract_pdf_text(uploaded_file) -> ExtractedPdf:
    """Extract plain text from a Streamlit uploaded PDF file."""
    raw = uploaded_file.getvalue()
    doc = fitz.open(stream=raw, filetype="pdf")
    pages: list[str] = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
        text = normalize_text(text)
        pages.append(f"[第{i}页]\n{text}".strip())
    full_text = "\n\n".join(pages).strip()
    return ExtractedPdf(filename=uploaded_file.name, text=full_text, pages=pages)


def pdf_to_page_images(uploaded_file, *, max_pages: int | None = None, dpi: int = 160) -> list[bytes]:
    """Render PDF pages to PNG bytes for API OCR/vision recognition."""
    raw = uploaded_file.getvalue()
    doc = fitz.open(stream=raw, filetype="pdf")
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    images: list[bytes] = []
    total = len(doc) if max_pages is None else min(len(doc), max_pages)
    for idx in range(total):
        page = doc[idx]
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        images.append(pix.tobytes("png"))
    return images


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_japanese_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[。！？!?])\s*", cleaned)
    return [p.strip() for p in parts if p.strip()]


def stable_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def extract_json_from_text(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("模型输出中没有可解析的 JSON。")


def compact_text(text: str, max_chars: int = 120_000) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return head + "\n\n[中间内容因过长被省略]\n\n" + tail
