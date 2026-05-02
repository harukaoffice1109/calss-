from __future__ import annotations

import json
from typing import Any

from ai_client import call_ai, call_ai_vision
from pdf_utils import compact_text, extract_json_from_text, split_japanese_sentences, stable_id

SYSTEM_PROMPT = """你是高考日语教师的备课助教。你的任务是帮助老师在课堂上快速讲解试卷。
要求：
- 只处理非听力、非作文部分。
- 输出必须简洁、准确、适合课堂现场转述。
- 优先结合标准答案和答案解析，不要脱离题目乱讲。
- 如果不确定，明确写“可能”。不要编造不存在的题干或选项。
- 所有结构化任务必须只输出合法 JSON，不要输出 Markdown 代码块。
"""

OCR_PROMPT = """你是严谨的日语试卷 OCR 助手。请识别图片中的文字。
要求：
- 按页面顺序输出。
- 尽量保留题号、选项、段落换行和日文假名汉字。
- 不要解释，不要总结，不要改写。
- 看不清的地方用 [?] 标记。
"""


def ocr_images_to_text(page_images: list[bytes], *, label: str, batch_size: int = 3) -> str:
    chunks: list[str] = []
    for start in range(0, len(page_images), batch_size):
        batch = page_images[start : start + batch_size]
        page_range = f"第{start + 1}-{start + len(batch)}页"
        user_text = f"请OCR识别这份{label}的{page_range}。只输出识别文本。"
        text = call_ai_vision(OCR_PROMPT, user_text, batch, temperature=0.0)
        chunks.append(f"[{label}{page_range}]\n{text.strip()}")
    return "\n\n".join(chunks).strip()


def identify_structure(exam_text: str, answer_text: str) -> dict[str, Any]:
    prompt = f"""
请根据下面的高考日语/模拟卷文本和答案文本，识别需要处理的部分。

只保留：
1. 日语知识运用/语言知识运用/语法词汇选择题
2. 阅读理解部分，每篇阅读文章和其对应选择题

跳过：
1. 听力
2. 作文/写作

请输出严格 JSON，格式如下：
{{
  "title": "试卷名称，无法判断则写高考日语试卷",
  "answer_map": {{"16": "A", "17": "B"}},
  "blocks": [
    {{
      "block_id": "knowledge_1",
      "type": "knowledge",
      "title": "日语知识运用",
      "question_range": "16-30",
      "exam_text": "该题块的题干和选项原文，尽量完整",
      "answer_text": "答案文本中对应解析，若没有则为空",
      "enabled": true
    }},
    {{
      "block_id": "reading_1",
      "type": "reading",
      "title": "阅读理解（一）",
      "question_range": "31-35",
      "article_text": "阅读文章全文",
      "questions_text": "该阅读对应题目和选项",
      "answer_text": "答案文本中对应解析，若没有则为空",
      "enabled": true
    }}
  ]
}}

注意：
- block_id 使用 knowledge_1, knowledge_2, reading_1, reading_2 这种稳定编号。
- 阅读必须按“每篇文章 + 对应题目”分块。
- exam_text/article_text/questions_text 不要写省略号，尽量从原文摘出完整内容。

【试卷文本】
{compact_text(exam_text)}

【答案文本】
{compact_text(answer_text, 100_000)}
"""
    raw = call_ai(SYSTEM_PROMPT, prompt, temperature=0.1)
    data = extract_json_from_text(raw)
    if not isinstance(data, dict):
        raise ValueError("结构识别结果不是 JSON 对象。")
    data.setdefault("blocks", [])
    data.setdefault("answer_map", {})
    return data


def analyze_block(block: dict[str, Any], answer_map: dict[str, str]) -> dict[str, Any]:
    if block.get("type") == "reading":
        return analyze_reading_block(block, answer_map)
    return analyze_knowledge_block(block, answer_map)


def analyze_knowledge_block(block: dict[str, Any], answer_map: dict[str, str]) -> dict[str, Any]:
    prompt = f"""
请分析下面的高考日语知识运用题块。输出严格 JSON，不要 Markdown。

输出格式：
{{
  "block_id": "{block.get('block_id')}",
  "type": "knowledge",
  "title": "{block.get('title')}",
  "summary": "本题块考点概览，100字以内",
  "questions": [
    {{
      "number": "16",
      "answer": "A",
      "question_text": "题干",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "quick": "10秒内能讲完的解释",
      "grammar": "相关语法/词义/接续说明，简洁",
      "option_analysis": {{"A": "为什么对/错", "B": "为什么对/错"}},
      "teacher_script": "老师课堂上可以直接这样说",
      "possible_followups": [{{"q": "学生可能追问", "a": "简短回答"}}]
    }}
  ]
}}

【题块】
{block.get('exam_text', '')}

【标准答案总表】
{json.dumps(answer_map, ensure_ascii=False)}

【答案解析文本】
{block.get('answer_text', '')}
"""
    raw = call_ai(SYSTEM_PROMPT, prompt, temperature=0.15)
    data = extract_json_from_text(raw)
    return _ensure_block_defaults(data, block)


def analyze_reading_block(block: dict[str, Any], answer_map: dict[str, str]) -> dict[str, Any]:
    prompt = f"""
请分析下面的高考日语阅读题块。输出严格 JSON，不要 Markdown。

输出格式：
{{
  "block_id": "{block.get('block_id')}",
  "type": "reading",
  "title": "{block.get('title')}",
  "article_summary": "文章大意，100字以内",
  "paragraph_logic": "段落/论证逻辑，简洁",
  "sentences": [
    {{
      "sentence_id": "r1_s1",
      "text": "日语原句",
      "translation": "自然中文翻译",
      "structure": "句子主干和修饰关系",
      "grammar": "最可能被学生问到的语法/助词/变形",
      "teacher_script": "老师课堂上可以直接这样讲",
      "possible_followups": [{{"q": "学生可能追问", "a": "简短回答"}}]
    }}
  ],
  "questions": [
    {{
      "number": "31",
      "answer": "B",
      "question_text": "题干",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "basis": "原文依据",
      "quick": "10秒内能讲完的解题理由",
      "option_analysis": {{"A": "错因", "B": "正确原因"}},
      "teacher_script": "老师课堂上可以直接这样说",
      "possible_followups": [{{"q": "学生可能追问", "a": "简短回答"}}]
    }}
  ]
}}

要求：
- sentences 要覆盖文章的主要句子；长句必须拆出结构和语法。
- questions 必须结合标准答案和答案解析。
- 内容要课堂可用，不要写成长篇论文。

【阅读文章】
{block.get('article_text', '')}

【题目与选项】
{block.get('questions_text', '')}

【标准答案总表】
{json.dumps(answer_map, ensure_ascii=False)}

【答案解析文本】
{block.get('answer_text', '')}
"""
    raw = call_ai(SYSTEM_PROMPT, prompt, temperature=0.15)
    data = extract_json_from_text(raw)
    data = _ensure_block_defaults(data, block)
    if not data.get("sentences") and block.get("article_text"):
        data["sentences"] = [
            {
                "sentence_id": f"{block.get('block_id', 'reading')}_s{i}",
                "text": s,
                "translation": "",
                "structure": "",
                "grammar": "",
                "teacher_script": "",
                "possible_followups": [],
            }
            for i, s in enumerate(split_japanese_sentences(block["article_text"]), start=1)
        ]
    return data


def emergency_followup(context: dict[str, Any], question: str) -> str:
    prompt = f"""
老师课堂上遇到临时追问。请基于已有解析，给出简洁、可直接转述的回答。

【已有上下文】
{json.dumps(context, ensure_ascii=False)[:12000]}

【学生问题】
{question}

输出格式：
简短回答：
课堂讲法：
如果继续追问：
"""
    return call_ai(SYSTEM_PROMPT, prompt, temperature=0.2)


def _ensure_block_defaults(data: Any, source_block: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("题块分析结果不是 JSON 对象。")
    data.setdefault("block_id", source_block.get("block_id", stable_id("block")))
    data.setdefault("type", source_block.get("type", "unknown"))
    data.setdefault("title", source_block.get("title", "未命名题块"))
    data.setdefault("questions", [])
    if data.get("type") == "reading":
        data.setdefault("sentences", [])
        data.setdefault("article_summary", "")
        data.setdefault("paragraph_logic", "")
    else:
        data.setdefault("summary", "")
    return data
