"""
侧边栏组件 - 豆包风格

深色侧边栏 + 会话历史 + 新建对话
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st


def render_sidebar():
    """渲染豆包风格侧边栏"""
    with st.sidebar:
        # 顶部 Logo + 标题
        st.markdown("""
        <div style="text-align: center; padding: 16px 0 20px 0;">
            <div style="font-size: 2rem; margin-bottom: 4px;">📋</div>
            <div style="color: white; font-size: 1.1rem; font-weight: 600;">智能合同审查</div>
            <div style="color: #888; font-size: 0.75rem; margin-top: 4px;">AI-Powered Contract Review</div>
        </div>
        """, unsafe_allow_html=True)

        # 新建对话按钮
        if st.button("✨ 新建对话", use_container_width=True, key="new_chat"):
            _new_conversation()

        # 文件上传
        _render_sidebar_upload()

        st.markdown("---")

        # 会话历史
        _render_session_history()

        st.markdown("---")

        # 快速操作
        _render_quick_actions()

        st.markdown("---")

        # 底部信息
        _render_footer_info()


def _new_conversation():
    """新建对话"""
    st.session_state["messages"] = []
    st.session_state["uploaded_file_content"] = None
    st.session_state["uploaded_file_name"] = None
    st.session_state["review_result"] = None
    st.session_state["_displayed_indices"] = set()
    st.rerun()


def _render_sidebar_upload():
    """渲染侧边栏文件上传"""
    # 如果已上传文件，显示文件信息
    if st.session_state.get("uploaded_file_name"):
        st.markdown(f"""
        <div style="background: rgba(79,70,229,0.15); border-radius: 8px; padding: 8px 12px;
                    margin: 8px 0; font-size: 0.85rem; color: #e0e0e0;">
            📎 {st.session_state['uploaded_file_name'][:25]}
        </div>
        """, unsafe_allow_html=True)
        if st.button("🗑️ 清除文件", use_container_width=True, key="sidebar_clear_file"):
            st.session_state["uploaded_file_content"] = None
            st.session_state["uploaded_file_name"] = None
            st.rerun()
    else:
        uploaded_file = st.file_uploader(
            "📎 上传合同",
            type=["txt", "pdf", "docx"],
            help="支持 TXT、PDF、DOCX",
            key="sidebar_file_uploader",
            label_visibility="collapsed"
        )
        if uploaded_file is not None:
            # 读取文件
            try:
                if uploaded_file.name.endswith(".txt"):
                    content = uploaded_file.read().decode("utf-8")
                elif uploaded_file.name.endswith(".pdf"):
                    import PyPDF2, io
                    pdf = PyPDF2.PdfReader(io.BytesIO(uploaded_file.read()))
                    content = "\n".join(p.extract_text() for p in pdf.pages)
                elif uploaded_file.name.endswith(".docx"):
                    import docx, io
                    doc = docx.Document(io.BytesIO(uploaded_file.read()))
                    content = "\n".join(p.text for p in doc.paragraphs)
                else:
                    content = None

                if content:
                    st.session_state["uploaded_file_content"] = content
                    st.session_state["uploaded_file_name"] = uploaded_file.name
                    st.rerun()
                else:
                    st.error("文件读取失败")
            except Exception as e:
                st.error(f"读取错误: {e}")


def _render_session_history():
    """渲染会话历史列表"""
    st.markdown("### 📝 对话历史")

    history = st.session_state.get("review_history", [])

    if not history:
        st.markdown("""
        <div style="color: #888; font-size: 0.85rem; padding: 8px 0; text-align: center;">
            暂无对话记录
        </div>
        """, unsafe_allow_html=True)
        return

    # 显示最近 10 条
    for i, record in enumerate(reversed(history[-10:])):
        name = record.get("contract_name", "未命名合同")
        ts = record.get("timestamp", "")
        status = record.get("status", "unknown")

        # 状态图标
        status_icon = {"completed": "✅", "failed": "❌"}.get(status, "❓")

        # 简短时间
        short_time = ts.split(" ")[-1][:5] if " " in ts else ts[:5]

        # 使用按钮模拟历史项
        label = f"{status_icon} {name[:20]}"
        if st.button(label, key=f"hist_{i}", use_container_width=True):
            _load_history_record(record)


def _load_history_record(record):
    """加载历史记录"""
    result = record.get("result", {})
    question = record.get("question", "查看审查结果")
    file_name = record.get("contract_name", "未命名合同")

    # 将历史记录的消息恢复到对话中
    st.session_state["messages"] = [
        {
            "role": "user",
            "content": question,
            "timestamp": record.get("timestamp", "")[-8:]
        },
        {
            "role": "assistant",
            "content": f"📋 **{file_name}** 的审查结果\n\n"
                       f"审查时间: {record.get('timestamp', 'N/A')}\n\n"
                       f"状态: {record.get('status', 'unknown')}",
            "timestamp": record.get("timestamp", "")[-8:]
        }
    ]

    if result:
        from frontend.components.chat import _format_answer
        answer = _format_answer(result, question, file_name)
        st.session_state["messages"].append({
            "role": "assistant",
            "content": answer,
            "timestamp": record.get("timestamp", "")[-8:]
        })

    st.rerun()


def _render_quick_actions():
    """渲染快速操作"""
    st.markdown("### ⚡ 快速操作")

    if st.button("🗑️ 清空对话", use_container_width=True, key="clear_all"):
        _clear_all()

    if st.button("📥 导出记录", use_container_width=True, key="export"):
        _export_history()


def _clear_all():
    """清空所有数据"""
    st.session_state["messages"] = []
    st.session_state["review_history"] = []
    st.session_state["uploaded_file_content"] = None
    st.session_state["uploaded_file_name"] = None
    st.session_state["review_result"] = None
    st.session_state["_displayed_indices"] = set()
    st.rerun()


def _export_history():
    """导出历史记录"""
    history = st.session_state.get("review_history", [])
    if not history:
        st.sidebar.info("暂无记录可导出")
        return

    import json
    export_data = json.dumps(history, ensure_ascii=False, indent=2, default=str)
    st.sidebar.download_button(
        label="📥 下载 JSON",
        data=export_data,
        file_name="contract_review_history.json",
        mime="application/json",
        key="download_history"
    )


def _render_footer_info():
    """渲染底部信息"""
    st.markdown("""
    <div style="color: #666; font-size: 0.75rem; padding: 8px 0; line-height: 1.6;">
        <div style="margin-bottom: 4px;">
            <span style="color: #888;">模型</span>
            <span style="color: #aaa;">MIMO v2.5</span>
        </div>
        <div style="margin-bottom: 4px;">
            <span style="color: #888;">版本</span>
            <span style="color: #aaa;">v1.0.0</span>
        </div>
        <div>
            <span style="color: #888;">框架</span>
            <span style="color: #aaa;">LangChain + Streamlit</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
