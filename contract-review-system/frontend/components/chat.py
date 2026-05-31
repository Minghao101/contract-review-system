"""
对话界面组件 - 类豆包风格：上传文件 + 对话提问
"""
import sys
import logging
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import requests

logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000/api/v1"


def render_chat_interface():
    """渲染对话界面"""
    # 初始化 session state
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "uploaded_file_content" not in st.session_state:
        st.session_state["uploaded_file_content"] = None
    if "uploaded_file_name" not in st.session_state:
        st.session_state["uploaded_file_name"] = None
    if "review_result" not in st.session_state:
        st.session_state["review_result"] = None

    # 欢迎消息
    if not st.session_state["messages"]:
        st.session_state["messages"].append({
            "role": "assistant",
            "content": "👋 你好！我是智能合同审查助手。\n\n请上传合同文件（PDF/DOCX/TXT），我会先分析合同内容，然后你可以针对合同提问。",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    # 渲染消息列表
    for msg in st.session_state["messages"]:
        _render_message(msg)

    # 输入区域
    st.markdown("---")

    # 文件上传（在输入框上方）
    _render_file_upload_area()

    # 对话输入
    user_input = st.chat_input("上传文件后，在这里输入问题...")

    if user_input:
        _handle_user_input(user_input)


def _render_file_upload_area():
    """渲染文件上传区域"""
    # 如果已有文件，显示已上传状态
    if st.session_state.get("uploaded_file_name"):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.info(f"📎 已上传: **{st.session_state['uploaded_file_name']}**")
        with col2:
            if st.button("✕ 清除", key="clear_file"):
                st.session_state["uploaded_file_content"] = None
                st.session_state["uploaded_file_name"] = None
                st.session_state["review_result"] = None
                st.rerun()
    else:
        # 文件上传组件
        uploaded_file = st.file_uploader(
            "📎 上传合同文件",
            type=["txt", "pdf", "docx"],
            help="支持 TXT、PDF、DOCX 格式",
            key="chat_file_uploader",
            label_visibility="collapsed"
        )

        if uploaded_file is not None:
            content = _read_uploaded_file(uploaded_file)
            if content:
                st.session_state["uploaded_file_content"] = content
                st.session_state["uploaded_file_name"] = uploaded_file.name
                st.success(f"✅ {uploaded_file.name} 上传成功（{len(content)} 字符）")
                st.rerun()
            else:
                st.error("❌ 文件读取失败")


def _read_uploaded_file(uploaded_file) -> str:
    """读取上传的文件内容"""
    try:
        if uploaded_file.name.endswith(".txt"):
            return uploaded_file.read().decode("utf-8")

        elif uploaded_file.name.endswith(".pdf"):
            import PyPDF2
            import io
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(uploaded_file.read()))
            return "\n".join(page.extract_text() for page in pdf_reader.pages)

        elif uploaded_file.name.endswith(".docx"):
            import docx
            import io
            doc = docx.Document(io.BytesIO(uploaded_file.read()))
            return "\n".join(para.text for para in doc.paragraphs)

        return None
    except Exception as e:
        st.error(f"文件读取错误: {e}")
        return None


def _render_message(msg: dict):
    """渲染单条消息"""
    role = msg["role"]
    content = msg["content"]
    timestamp = msg.get("timestamp", "")

    with st.chat_message(role):
        st.markdown(content)
        if timestamp:
            st.caption(f"🕐 {timestamp}")


def _handle_user_input(user_input: str):
    """处理用户输入"""
    # 添加用户消息
    st.session_state["messages"].append({
        "role": "user",
        "content": user_input,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    # 获取上传的文件内容
    contract_text = st.session_state.get("uploaded_file_content")
    file_name = st.session_state.get("uploaded_file_name", "未知文件")

    if not contract_text:
        # 没有上传文件，提示用户
        st.session_state["messages"].append({
            "role": "assistant",
            "content": "⚠️ 请先上传合同文件，然后我才能帮你分析。",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        st.rerun()
        return

    # 有文件，调用后端分析
    _process_with_backend(contract_text, user_input, file_name)


def _process_with_backend(contract_text: str, question: str, file_name: str):
    """调用后端处理"""
    with st.spinner("🔄 正在分析..."):
        try:
            # 调用同步审查接口，把问题作为 review_focus
            response = requests.post(
                f"{API_BASE_URL}/review/sync",
                json={
                    "contract_text": contract_text,
                    "contract_type": "general",
                    "review_focus": [question]
                },
                timeout=300
            )

            if response.status_code == 200:
                result = response.json()
                st.session_state["review_result"] = result

                # 格式化回答
                answer = _format_answer(result, question, file_name)

                st.session_state["messages"].append({
                    "role": "assistant",
                    "content": answer,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            else:
                st.session_state["messages"].append({
                    "role": "assistant",
                    "content": f"❌ 后端错误: {response.status_code}",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

        except requests.exceptions.ConnectionError:
            st.session_state["messages"].append({
                "role": "assistant",
                "content": "❌ 无法连接到后端服务，请确认 FastAPI 已启动。\n\n```\n.venv\\Scripts\\python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000\n```",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"处理失败: {e}\n{tb}")
            st.session_state["messages"].append({
                "role": "assistant",
                "content": f"❌ 处理失败: {str(e)}\n\n```\n{tb[-500:]}\n```",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

    st.rerun()


def _to_str(item) -> str:
    """安全转换为字符串，保证返回 str"""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("description", "text", "title", "content", "summary"):
            val = item.get(key)
            if isinstance(val, str) and val:
                return val
        return str(item)
    return str(item)


def _format_answer(result: dict, question: str, file_name: str) -> str:
    """根据审查结果和用户问题，格式化回答"""
    lines = [f"针对您的问题「{question}」，以下是分析结果：\n"]

    # 文档基本信息
    if result.get("document_info"):
        info = result["document_info"]
        lines.append(f"📄 **文件**: {file_name}")
        if info.get("contract_type"):
            lines.append(f"📋 **合同类型**: {info['contract_type']}")
        if info.get("basic_info"):
            bi = info["basic_info"]
            if bi.get("parties"):
                lines.append(f"👥 **当事方**: {', '.join(str(p) for p in bi['parties'])}")
        lines.append("")

    # 风险评估
    if result.get("risks"):
        lines.append("### ⚠️ 风险评估")
        for r in result["risks"]:
            if isinstance(r, dict):
                level = r.get("level", r.get("severity", "medium"))
                emoji = {"high": "🔴", "critical": "🔴", "medium": "🟡", "low": "🟢"}.get(level, "⚪")
                title = _to_str(r.get("title", r.get("name", "风险")))
                desc = _to_str(r.get("description", ""))[:150]
                lines.append(f"- {emoji} **{title}**: {desc}")
            else:
                lines.append(f"- ⚠️ {_to_str(r)}")
        lines.append("")

    # 合规检查
    if result.get("compliance_violations"):
        lines.append("### ✅ 合规问题")
        for v in result["compliance_violations"]:
            lines.append(f"- ⚠️ {_to_str(v)}")
        lines.append("")

    if result.get("missing_clauses"):
        lines.append("### 📋 缺失条款")
        for c in result["missing_clauses"]:
            lines.append(f"- ❌ {_to_str(c)}")
        lines.append("")

    # 条款分析摘要
    if result.get("clause_analysis"):
        analysis = result["clause_analysis"]
        if isinstance(analysis, dict):
            lines.append("### 📝 条款分析")
            # 总体评估
            if analysis.get("overall_assessment"):
                lines.append(_to_str(analysis["overall_assessment"]))
            elif analysis.get("summary"):
                lines.append(_to_str(analysis["summary"]))
            # 统计信息
            if analysis.get("total_clauses"):
                lines.append(f"- 条款总数: {analysis['total_clauses']}")
            if analysis.get("total_issues"):
                lines.append(f"- 发现问题: {analysis['total_issues']}")
            # 关键建议
            if analysis.get("key_recommendations"):
                lines.append("")
                lines.append("**关键建议:**")
                for rec in analysis["key_recommendations"]:
                    lines.append(f"- {_to_str(rec)}")
            lines.append("")

    # 报告摘要
    if result.get("summary"):
        summary = result["summary"]
        lines.append("### 📊 综合摘要")
        if isinstance(summary, str):
            lines.append(summary)
        elif isinstance(summary, dict):
            text = summary.get("text") or summary.get("content") or ""
            if text:
                lines.append(_to_str(text))
            else:
                for k, v in summary.items():
                    if v and isinstance(v, str):
                        lines.append(f"- **{k}**: {v[:200]}")
        lines.append("")

    # 建议
    if result.get("recommendations"):
        lines.append("### 💡 建议")
        for rec in result["recommendations"]:
            lines.append(f"- {_to_str(rec)}")

    if len(lines) <= 1:
        lines.append("分析完成，但未找到相关信息。")

    return "\n".join(str(line) for line in lines)
