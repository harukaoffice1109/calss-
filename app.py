from __future__ import annotations

from typing import Any

import streamlit as st

from ai_client import get_secret
from pdf_utils import extract_pdf_text
from prompts import analyze_block, emergency_followup, identify_structure
from storage import block_label, build_analysis_package, load_package, package_to_bytes, question_label

st.set_page_config(page_title="高考日语课堂小助手", page_icon="📘", layout="wide")

CSS = """
<style>
.main .block-container { padding-top: 1.2rem; max-width: 1100px; }
.jp-sentence { font-size: 1.02rem; line-height: 1.65; }
.stButton button { border-radius: 10px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def check_password() -> bool:
    password = get_secret("APP_PASSWORD", "")
    if not password:
        return True
    if st.session_state.get("authed"):
        return True
    st.title("📘 高考日语课堂小助手")
    entered = st.text_input("访问密码", type="password")
    if st.button("进入"):
        if entered == password:
            st.session_state.authed = True
            st.rerun()
        st.error("密码不正确")
    return False


def render_selected_item() -> None:
    item = st.session_state.get("selected_item")
    if not item:
        st.info("点击上面的句子或题号后，这里会显示解析。")
        return

    st.divider()
    if "text" in item and "translation" in item:
        st.markdown("### 句子解析")
        st.markdown(f"**原句：** {item.get('text', '')}")
        st.markdown(f"**翻译：** {item.get('translation', '')}")
        st.markdown(f"**结构：** {item.get('structure', '')}")
        st.markdown(f"**语法/变形：** {item.get('grammar', '')}")
        if item.get("teacher_script"):
            st.success(item.get("teacher_script"))
        followups = item.get("possible_followups", []) or []
        if followups:
            with st.expander("学生可能追问"):
                for qa in followups:
                    st.write(f"**Q：** {qa.get('q', '')}")
                    st.write(f"**A：** {qa.get('a', '')}")
    else:
        st.markdown("### 题目解析")
        st.markdown(f"**题号：** {item.get('number', '')}　**答案：** {item.get('answer', '')}")
        if item.get("question_text"):
            st.markdown(f"**题干：** {item.get('question_text')}")
        if item.get("basis"):
            st.markdown(f"**原文依据：** {item.get('basis')}")
        if item.get("quick"):
            st.markdown(f"**快速解释：** {item.get('quick')}")
        if item.get("grammar"):
            st.markdown(f"**考点：** {item.get('grammar')}")
        if item.get("teacher_script"):
            st.success(item.get("teacher_script"))
        options = item.get("options") or {}
        analysis = item.get("option_analysis") or {}
        if options or analysis:
            with st.expander("选项分析", expanded=True):
                keys = sorted(set(options.keys()) | set(analysis.keys()))
                for key in keys:
                    st.write(f"**{key}. {options.get(key, '')}**")
                    st.write(analysis.get(key, ""))
        followups = item.get("possible_followups", []) or []
        if followups:
            with st.expander("学生可能追问"):
                for qa in followups:
                    st.write(f"**Q：** {qa.get('q', '')}")
                    st.write(f"**A：** {qa.get('a', '')}")


def render_reading_block(block: dict[str, Any]) -> None:
    st.markdown(f"### {block.get('title', '阅读理解')}")
    if block.get("article_summary"):
        with st.expander("文章总览", expanded=True):
            st.write(block.get("article_summary", ""))
            if block.get("paragraph_logic"):
                st.write("**段落逻辑：**")
                st.write(block.get("paragraph_logic"))

    st.markdown("#### 句子点读")
    for i, sent in enumerate(block.get("sentences", []), start=1):
        cols = st.columns([0.18, 0.82])
        with cols[0]:
            if st.button(f"句{i}", key=f"sent_{block.get('block_id')}_{i}"):
                st.session_state.selected_item = sent
        with cols[1]:
            st.markdown(f"<div class='jp-sentence'>{sent.get('text', '')}</div>", unsafe_allow_html=True)

    st.markdown("#### 题目")
    for q in block.get("questions", []):
        if st.button(question_label(q), key=f"q_{block.get('block_id')}_{q.get('number')}", use_container_width=True):
            st.session_state.selected_item = q

    render_selected_item()


def render_knowledge_block(block: dict[str, Any]) -> None:
    st.markdown(f"### {block.get('title', '日语知识运用')}")
    if block.get("summary"):
        st.info(block.get("summary"))
    for q in block.get("questions", []):
        if st.button(question_label(q), key=f"kq_{block.get('block_id')}_{q.get('number')}", use_container_width=True):
            st.session_state.selected_item = q
    render_selected_item()


def render_block(block: dict[str, Any]) -> None:
    if block.get("type") == "reading":
        render_reading_block(block)
    else:
        render_knowledge_block(block)


def init_state() -> None:
    defaults = {
        "structure": None,
        "exam_text": "",
        "answer_text": "",
        "analysis_pkg": None,
        "selected_item": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


if not check_password():
    st.stop()

init_state()

st.title("📘 高考日语课堂小助手")
st.caption("课前按题块生成解析包；课堂点击句子/题号，直接秒出分析。默认跳过听力和作文。")

tab_create, tab_class, tab_help = st.tabs(["① 创建解析包", "② 课堂模式", "③ 临时追问"])

with tab_create:
    st.subheader("创建解析包")
    st.write("先上传试卷 PDF 和答案 PDF，系统会识别非听力、非作文部分，再按题块预处理。")

    col1, col2 = st.columns(2)
    with col1:
        exam_pdf = st.file_uploader("试卷 PDF", type=["pdf"], key="exam_pdf")
    with col2:
        answer_pdf = st.file_uploader("答案 PDF", type=["pdf"], key="answer_pdf")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("提取文本", use_container_width=True, disabled=not exam_pdf):
            with st.spinner("正在提取 PDF 文本……"):
                exam = extract_pdf_text(exam_pdf)
                st.session_state.exam_text = exam.text
                if answer_pdf:
                    ans = extract_pdf_text(answer_pdf)
                    st.session_state.answer_text = ans.text
                else:
                    st.session_state.answer_text = ""
            st.success("文本提取完成")
    with c2:
        if st.button("识别试卷结构", use_container_width=True, disabled=not st.session_state.exam_text):
            with st.spinner("正在识别知识运用和阅读理解题块……"):
                st.session_state.structure = identify_structure(st.session_state.exam_text, st.session_state.answer_text)
            st.success("结构识别完成")

    if st.session_state.exam_text:
        with st.expander("查看提取文本预览", expanded=False):
            st.text_area("试卷文本", st.session_state.exam_text[:8000], height=220)
            if st.session_state.answer_text:
                st.text_area("答案文本", st.session_state.answer_text[:5000], height=160)

    structure = st.session_state.structure
    if structure:
        st.divider()
        st.subheader("确认要处理的题块")
        st.caption("识别不准时，第一版可先取消明显错误的块；后续可以继续增强手动编辑。")
        st.write(f"试卷名称：{structure.get('title', '高考日语试卷')}")
        blocks = structure.get("blocks", [])
        selected_indices: list[int] = []
        for idx, block in enumerate(blocks):
            default = bool(block.get("enabled", True)) and block.get("type") in {"knowledge", "reading"}
            label = f"{idx + 1}. {block_label(block)} - {block.get('type')}"
            if st.checkbox(label, value=default, key=f"block_enabled_{idx}"):
                selected_indices.append(idx)
            preview = block.get("article_text") or block.get("exam_text") or block.get("questions_text") or ""
            if preview:
                st.caption(preview[:180].replace("\n", " ") + ("……" if len(preview) > 180 else ""))

        if st.button("生成课堂解析包", type="primary", use_container_width=True, disabled=not selected_indices):
            analyzed: list[dict[str, Any]] = []
            progress = st.progress(0)
            status = st.empty()
            for pos, idx in enumerate(selected_indices, start=1):
                block = blocks[idx]
                status.info(f"正在处理：{block_label(block)}")
                analyzed_block = analyze_block(block, structure.get("answer_map", {}))
                if block.get("question_range") and not analyzed_block.get("question_range"):
                    analyzed_block["question_range"] = block.get("question_range")
                analyzed.append(analyzed_block)
                progress.progress(pos / len(selected_indices))
            pkg = build_analysis_package(structure.get("title", "高考日语试卷"), structure, analyzed)
            st.session_state.analysis_pkg = pkg
            status.success("解析包生成完成")

    if st.session_state.analysis_pkg:
        st.download_button(
            "下载课堂解析包 analysis.json",
            data=package_to_bytes(st.session_state.analysis_pkg),
            file_name=f"{st.session_state.analysis_pkg.get('title', '高考日语试卷')}.analysis.json",
            mime="application/json",
            use_container_width=True,
        )

with tab_class:
    st.subheader("课堂模式")
    uploaded_pkg = st.file_uploader("上传已生成的 analysis.json；如果刚刚已生成，可不用上传", type=["json"], key="analysis_json")
    if uploaded_pkg:
        try:
            st.session_state.analysis_pkg = load_package(uploaded_pkg)
            st.success("解析包已加载")
        except Exception as exc:
            st.error(f"解析包读取失败：{exc}")

    pkg = st.session_state.analysis_pkg
    if not pkg:
        st.info("请先在“创建解析包”生成解析包，或上传已有 analysis.json。")
    else:
        st.write(f"当前试卷：**{pkg.get('title', '高考日语试卷')}**")
        blocks = pkg.get("blocks", [])
        if not blocks:
            st.warning("解析包里没有题块。")
        else:
            labels = [block_label(b) for b in blocks]
            selected_label = st.selectbox("选择题块", labels)
            block = blocks[labels.index(selected_label)]
            render_block(block)

with tab_help:
    st.subheader("临时追问")
    st.caption("课堂上如果学生问了缓存里没有的问题，可以临时调用 API。平时不需要用。")
    pkg = st.session_state.analysis_pkg
    if not pkg:
        st.info("先加载解析包，追问回答会更准确。")
    question = st.text_area("学生追问 / 你想临时确认的问题", height=120, placeholder="例如：这里为什么用 に 而不是 で？")
    if st.button("临时回答", disabled=not question.strip(), use_container_width=True):
        context = st.session_state.selected_item or {"package_title": pkg.get("title") if pkg else ""}
        with st.spinner("正在生成临时回答……"):
            answer = emergency_followup(context, question.strip())
        st.markdown(answer)
