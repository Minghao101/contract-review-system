"""
智能合同审查系统 - 主界面

Streamlit 应用入口
"""
import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
from frontend.components.chat import render_chat_interface
from frontend.components.file_upload import render_file_upload
from frontend.components.sidebar import render_sidebar
from frontend.components.result_display import render_review_result


def main():
    """主应用入口"""
    st.set_page_config(
        page_title="智能合同审查系统",
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # 自定义样式
    _apply_custom_css()

    # 渲染侧边栏
    render_sidebar()

    # 主标题
    st.title("📋 智能合同审查系统")
    st.caption("基于多Agent协作的AI合同审查平台")

    # 选项卡
    tab_chat, tab_upload, tab_history = st.tabs([
        "💬 合同审查", "📄 文件上传", "📚 历史记录"
    ])

    with tab_chat:
        render_chat_interface()

    with tab_upload:
        render_file_upload()

    with tab_history:
        _render_history_tab()


def _render_history_tab():
    """渲染历史记录选项卡"""
    st.subheader("历史审查记录")

    # 从 session state 获取历史
    history = st.session_state.get("review_history", [])

    if not history:
        st.info("暂无历史记录。开始一次合同审查后，结果将显示在这里。")
        return

    for i, record in enumerate(reversed(history)):
        with st.expander(
            f"📋 {record.get('contract_name', '未命名合同')} - "
            f"{record.get('status', '未知')} - "
            f"{record.get('timestamp', '')}",
            expanded=False
        ):
            render_review_result(record)


def _apply_custom_css():
    """应用自定义CSS样式"""
    st.markdown("""
    <style>
    /* ========== 聊天消息样式 ========== */
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
    }
    .user-message {
        background-color: #e3f2fd;
        border-left: 4px solid #2196f3;
    }
    .assistant-message {
        background-color: #f5f5f5;
        border-left: 4px solid #4caf50;
    }

    /* ========== 状态标签 ========== */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.5rem;
        border-radius: 1rem;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .status-completed {
        background-color: #c8e6c9;
        color: #2e7d32;
    }
    .status-failed {
        background-color: #ffcdd2;
        color: #c62828;
    }
    .status-processing {
        background-color: #fff3e0;
        color: #e65100;
    }

    /* ========== 进度条 ========== */
    .progress-bar {
        height: 4px;
        background-color: #e0e0e0;
        border-radius: 2px;
        overflow: hidden;
    }
    .progress-fill {
        height: 100%;
        background-color: #2196f3;
        transition: width 0.3s ease;
    }

    /* ========== 结果卡片样式 ========== */
    .result-card {
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        transition: box-shadow 0.2s ease;
    }
    .result-card:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    .result-card-success {
        border-left: 4px solid #4caf50;
        background-color: #c8e6c9;
    }
    .result-card-warning {
        border-left: 4px solid #ff9800;
        background-color: #fff3e0;
    }
    .result-card-error {
        border-left: 4px solid #f44336;
        background-color: #ffcdd2;
    }
    .result-card-info {
        border-left: 4px solid #2196f3;
        background-color: #e3f2fd;
    }

    /* ========== 指标卡片 ========== */
    .metric-card {
        text-align: center;
        padding: 12px;
        border-radius: 8px;
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: bold;
        color: #333;
    }
    .metric-label {
        font-size: 0.8rem;
        color: #666;
        margin-top: 4px;
    }

    /* ========== 时间线样式 ========== */
    .timeline-item {
        display: flex;
        align-items: center;
        padding: 6px 0;
        border-left: 3px solid #e0e0e0;
        margin-left: 10px;
        padding-left: 15px;
        margin-bottom: 4px;
    }
    .timeline-item-completed {
        border-left-color: #4caf50;
    }
    .timeline-item-running {
        border-left-color: #2196f3;
    }
    .timeline-item-failed {
        border-left-color: #f44336;
    }

    /* ========== 报告头部渐变 ========== */
    .report-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .report-header h2 {
        margin: 0;
        color: white;
    }

    /* ========== Agent状态卡片 ========== */
    .agent-status {
        display: flex;
        align-items: center;
        padding: 10px 14px;
        border-radius: 8px;
        margin-bottom: 6px;
        transition: background-color 0.2s ease;
    }

    /* ========== 动画 ========== */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .fade-in {
        animation: fadeIn 0.3s ease-out;
    }

    /* ========== 按钮优化 ========== */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }

    /* ========== 风险分布条 ========== */
    .risk-distribution {
        display: flex;
        height: 24px;
        border-radius: 12px;
        overflow: hidden;
        margin-bottom: 8px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
