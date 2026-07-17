"""
对话界面组件 - 豆包风格
"""
import sys
import logging
import time
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import requests

logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8001/api/v1"


def render_chat_interface():
    """渲染豆包风格聊天界面"""
    # 初始化 session state
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "uploaded_file_content" not in st.session_state:
        st.session_state["uploaded_file_content"] = None
    if "uploaded_file_name" not in st.session_state:
        st.session_state["uploaded_file_name"] = None
    if "review_result" not in st.session_state:
        st.session_state["review_result"] = None
    if "_displayed_indices" not in st.session_state:
        st.session_state["_displayed_indices"] = set()
    if "session_id" not in st.session_state:
        import uuid
        st.session_state["session_id"] = str(uuid.uuid4())

    # 每次脚本执行开始时清除已显示标记，确保消息正常渲染
    # _displayed_indices 仅用于当前执行中防止流式输出/错误消息重复渲染
    st.session_state["_displayed_indices"] = set()

    # 页面标题
    _render_header()

    # 已上传文件提示
    if st.session_state.get("uploaded_file_name"):
        _render_file_banner()

    # 消息列表
    if not st.session_state["messages"]:
        _render_welcome()
    else:
        _render_messages()

    # 输入区域
    _render_input_area()


def _render_header():
    """渲染页面标题"""
    st.markdown("""
    <div class="doubao-header">
        <h1>📋 智能合同审查</h1>
        <p>上传合同文件，AI 帮你分析风险、检查合规、生成报告</p>
    </div>
    """, unsafe_allow_html=True)


def _render_welcome():
    """渲染欢迎页面"""
    st.markdown("""
    <div class="welcome-card">
        <h2>👋 你好，我是合同审查助手</h2>
        <p>我可以帮你：</p>
        <p>
            <span class="feature-tag">📄 解析合同结构</span>
            <span class="feature-tag">⚠️ 评估风险等级</span>
            <span class="feature-tag">✅ 检查合规性</span>
            <span class="feature-tag">📊 生成审查报告</span>
        </p>
        <p style="margin-top: 12px; font-size: 0.85rem; opacity: 0.8;">
            👈 请在左侧侧边栏上传合同文件
        </p>
    </div>
    """, unsafe_allow_html=True)


def _render_file_banner():
    """渲染已上传文件提示"""
    col1, col2 = st.columns([5, 1])
    with col1:
        st.info(f"📎 已上传: **{st.session_state['uploaded_file_name']}**")
    with col2:
        if st.button("✕", key="clear_file", help="清除文件"):
            st.session_state["uploaded_file_content"] = None
            st.session_state["uploaded_file_name"] = None
            st.session_state["review_result"] = None
            st.rerun()


def _render_messages():
    """渲染消息列表"""
    # 获取已直接显示的消息索引（流式输出/错误提示已渲染的）
    displayed_indices = st.session_state.get("_displayed_indices", set())

    for idx, msg in enumerate(st.session_state["messages"]):
        # 跳过已在当前脚本执行中直接显示的消息
        if idx in displayed_indices:
            continue

        role = msg["role"]
        content = msg["content"]
        timestamp = msg.get("timestamp", "")

        avatar = "🤖" if role == "assistant" else "👤"

        with st.chat_message(role, avatar=avatar):
            st.markdown(content)
            if timestamp:
                st.caption(f"🕐 {timestamp}")


def _render_input_area():
    """渲染底部输入区域"""
    # 显示当前文件状态
    if st.session_state.get("uploaded_file_name"):
        st.caption(f"📎 当前文件: {st.session_state['uploaded_file_name']}")

    # 聊天输入
    user_input = st.chat_input("输入你的问题，例如：这个合同有什么风险？")

    if user_input:
        _handle_user_input(user_input)


def _handle_user_input(user_input: str):
    """处理用户输入"""
    # 添加用户消息到 session state
    st.session_state["messages"].append({
        "role": "user",
        "content": user_input,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })

    # 立即显示用户消息（不等待 rerun）
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)
    # 标记用户消息已直接显示
    user_idx = len(st.session_state["messages"]) - 1
    st.session_state.setdefault("_displayed_indices", set()).add(user_idx)

    # 获取上传的文件内容
    contract_text = st.session_state.get("uploaded_file_content")
    file_name = st.session_state.get("uploaded_file_name", "未知文件")

    # 特殊命令
    if user_input.strip() in ["查看历史", "历史记录", "查询记忆", "我的审查"]:
        _query_memory(user_input)
        st.rerun()
        return

    if not contract_text:
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown("⚠️ 请先上传合同文件，然后我才能帮你分析。\n\n你也可以输入「查看历史」来查看之前的审查记录。")
        st.session_state["messages"].append({
            "role": "assistant",
            "content": "⚠️ 请先上传合同文件，然后我才能帮你分析。\n\n你也可以输入「查看历史」来查看之前的审查记录。",
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })
        # 标记该消息已直接显示，避免 _render_messages 重复渲染
        idx = len(st.session_state["messages"]) - 1
        st.session_state.setdefault("_displayed_indices", set()).add(idx)
        st.rerun()
        return

    # 有文件，调用后端分析（流式输出）
    _process_with_backend(contract_text, user_input, file_name)


def _query_memory(query: str):
    """查询历史记忆"""
    try:
        response = requests.get(
            f"{API_BASE_URL}/memory/recall",
            params={"query": query, "top_k": 5},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            memories = data.get("memories", [])

            if memories:
                lines = ["## 📚 历史审查记忆\n"]
                for i, m in enumerate(memories, 1):
                    name = m.get("contract_name", "未知")
                    created = m.get("created_at", "")[:10]
                    summary = m.get("result_summary", {})
                    risk = summary.get("risk_level", "未知")
                    score = summary.get("compliance_score", "未知")
                    lines.append(f"**{i}. {name}** ({created})")
                    lines.append(f"   风险等级: {risk} | 合规分数: {score}")
                    lines.append("")
                content = "\n".join(lines)
            else:
                content = "📭 暂无历史审查记录。上传合同文件后，审查结果会自动保存。"
        else:
            content = "⚠️ 查询记忆失败，请确认后端服务已启动。"

    except requests.exceptions.ConnectionError:
        content = "❌ 无法连接到后端服务，请确认 FastAPI 已启动。"
    except Exception as e:
        content = f"❌ 查询失败: {str(e)}"

    st.session_state["messages"].append({
        "role": "assistant",
        "content": content,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })


def _process_with_backend(contract_text: str, question: str, file_name: str):
    """调用后端处理 - SSE 流式输出"""
    try:
        import json as _json

        response = requests.post(
            f"{API_BASE_URL}/review/stream_sse",
            json={
                "contract_text": contract_text,
                "contract_type": "general",
                "review_focus": [question],
                "contract_name": file_name,
                "session_id": st.session_state.get("session_id")
            },
            timeout=300,
            stream=True
        )

        if response.status_code != 200:
            error_msg = f"❌ 后端错误: {response.status_code}"
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(error_msg)
            st.session_state["messages"].append({
                "role": "assistant",
                "content": error_msg,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            })
            idx = len(st.session_state["messages"]) - 1
            st.session_state.setdefault("_displayed_indices", set()).add(idx)
            return

        # 解析 SSE 事件流
        status_placeholder = st.empty()
        result_content = ""
        current_event = None

        with st.chat_message("assistant", avatar="🤖"):
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                if line.startswith("event: "):
                    current_event = line[7:].strip()
                elif line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        data = _json.loads(data_str)
                    except Exception:
                        continue

                    if current_event == "progress":
                        msg = data.get("message", "")
                        status = data.get("status", "")
                        # 显示进度
                        if status in ("intent_recognizing", "intent_done", "agents_starting",
                                      "answering", "topic_discussing", "topic_agent_done",
                                      "topic_concluding", "processing"):
                            status_placeholder.caption(f"🔄 {msg}")

                    elif current_event == "chunk":
                        # 逐 token 流式输出（追问场景）
                        content = data.get("content", "")
                        if content:
                            result_content += content
                            status_placeholder.empty()
                            st.markdown(result_content)

                    elif current_event == "result":
                        # 最终结果
                        content = data.get("content", "")
                        if content:
                            result_content = content
                            status_placeholder.empty()
                            st.markdown(content)

                    elif current_event == "error":
                        msg = data.get("message", "未知错误")
                        status_placeholder.empty()
                        st.error(f"❌ {msg}")
                        result_content = f"❌ {msg}"

                    elif current_event == "done":
                        break

        # 保存到 session state
        if result_content:
            st.session_state["review_result"] = {"raw_text": result_content}

            if "review_history" not in st.session_state:
                st.session_state["review_history"] = []
            st.session_state["review_history"].append({
                "contract_name": file_name,
                "status": "completed",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "result": {"raw_text": result_content},
                "question": question
            })

            st.session_state["messages"].append({
                "role": "assistant",
                "content": result_content,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            })
            idx = len(st.session_state["messages"]) - 1
            st.session_state.setdefault("_displayed_indices", set()).add(idx)

    except requests.exceptions.ConnectionError:
        error_msg = (
            "❌ 无法连接到后端服务，请确认 FastAPI 已启动。\n\n"
            "```\n.venv\\Scripts\\python.exe -m uvicorn src.api.main:app "
            "--host 0.0.0.0 --port 8001\n```"
        )
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(error_msg)
        st.session_state["messages"].append({
            "role": "assistant",
            "content": error_msg,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })
        idx = len(st.session_state["messages"]) - 1
        st.session_state.setdefault("_displayed_indices", set()).add(idx)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"处理失败: {e}\n{tb}")
        error_msg = f"❌ 处理失败: {str(e)}\n\n```\n{tb[-500:]}\n```"
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(error_msg)
        st.session_state["messages"].append({
            "role": "assistant",
            "content": error_msg,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })
        idx = len(st.session_state["messages"]) - 1
        st.session_state.setdefault("_displayed_indices", set()).add(idx)


def _stream_answer(answer: str):
    """将回答以流式方式逐块输出到聊天界面"""
    def _text_generator():
        """逐块生成文本"""
        lines = answer.split("\n")
        for i, line in enumerate(lines):
            chunk = line + ("\n" if i < len(lines) - 1 else "")
            yield chunk

    with st.chat_message("assistant", avatar="🤖"):
        st.write_stream(_text_generator())

    # 保存完整消息到 session state
    st.session_state["messages"].append({
        "role": "assistant",
        "content": answer,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })
    # 标记该消息已直接显示，避免 _render_messages 重复渲染
    idx = len(st.session_state["messages"]) - 1
    st.session_state.setdefault("_displayed_indices", set()).add(idx)


def _to_str(item) -> str:
    """安全转换为字符串"""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("description", "text", "title", "content", "summary", "suggestion"):
            val = item.get(key)
            if isinstance(val, str) and val:
                return val
        return str(item)
    return str(item)


def _parse_rec(item):
    """尝试将recommendation项解析为dict，兼容字符串形式的JSON"""
    if isinstance(item, dict):
        return item
    if isinstance(item, str):
        import json as _json
        try:
            parsed = _json.loads(item)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return None


def _format_answer(result: dict, question: str, file_name: str) -> str:
    """根据审查结果和用户问题，格式化回答"""
    # 如果是追问类回答（question_answer），直接返回 response
    if result.get("response") and not result.get("risks") and not result.get("document_info"):
        return result["response"]

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
            r_dict = _parse_rec(r)
            if r_dict:
                level = r_dict.get("level", r_dict.get("severity", "medium"))
                emoji = {"high": "🔴", "critical": "🔴", "medium": "🟡", "low": "🟢"}.get(level, "⚪")
                title = _to_str(r_dict.get("title", r_dict.get("name", "风险")))
                desc = _to_str(r_dict.get("description", ""))[:150]
                lines.append(f"- {emoji} **{title}**: {desc}")
            else:
                lines.append(f"- ⚠️ {_to_str(r)}")
        lines.append("")

    # 合规检查
    if result.get("compliance_violations"):
        lines.append("### ✅ 合规问题")
        for v in result["compliance_violations"]:
            v_dict = _parse_rec(v)
            if v_dict:
                severity = v_dict.get("severity", "medium")
                emoji = {"high": "🔴", "critical": "🔴", "medium": "🟡", "low": "🟢"}.get(severity, "⚪")
                clause = _to_str(v_dict.get("clause", ""))
                regulation = v_dict.get("regulation", "")
                suggestion = _to_str(v_dict.get("suggestion", ""))
                if clause:
                    lines.append(f"- {emoji} **{clause}**")
                if regulation:
                    lines.append(f"  违规: {regulation}")
                if suggestion:
                    lines.append(f"  建议: {suggestion}")
            else:
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
            if analysis.get("overall_assessment"):
                lines.append(_to_str(analysis["overall_assessment"]))
            elif analysis.get("summary"):
                lines.append(_to_str(analysis["summary"]))
            if analysis.get("total_clauses"):
                lines.append(f"- 条款总数: {analysis['total_clauses']}")
            if analysis.get("total_issues"):
                lines.append(f"- 发现问题: {analysis['total_issues']}")
            if analysis.get("key_recommendations"):
                lines.append("")
                lines.append("**关键建议:**")
                for rec in analysis["key_recommendations"]:
                    rec_dict = _parse_rec(rec)
                    if rec_dict:
                        suggestion = _to_str(rec_dict.get("suggestion", rec_dict.get("description", rec)))
                        lines.append(f"- {suggestion}")
                    else:
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
            rec_dict = _parse_rec(rec)
            if rec_dict:
                priority = rec_dict.get("priority", "medium")
                emoji = {"high": "🔴", "critical": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
                category = rec_dict.get("category", "")
                suggestion = _to_str(rec_dict.get("suggestion", rec_dict.get("description", "")))
                reason = rec_dict.get("reason", "")
                if category:
                    lines.append(f"- {emoji} **[{priority}] {category}**: {suggestion}")
                else:
                    lines.append(f"- {emoji} **[{priority}]**: {suggestion}")
                if reason:
                    lines.append(f"  原因: {reason}")
            else:
                lines.append(f"- {_to_str(rec)}")

    if len(lines) <= 1:
        lines.append("分析完成，但未找到相关信息。")

    return "\n".join(str(line) for line in lines)


