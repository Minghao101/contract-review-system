"""
智能合同审查系统 - 主界面（豆包风格）

Streamlit 应用入口
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
from frontend.components.chat import render_chat_interface
from frontend.components.sidebar import render_sidebar


def main():
    """主应用入口"""
    st.set_page_config(
        page_title="智能合同审查",
        page_icon="📋",
        layout="centered",
        initial_sidebar_state="expanded"
    )

    # 自定义样式
    _apply_custom_css()

    # 渲染侧边栏
    render_sidebar()

    # 主内容区：聊天界面
    render_chat_interface()


def _apply_custom_css():
    """应用豆包风格CSS"""
    st.markdown("""
    <style>
    /* ========== 全局 ========== */
    .stApp {
        background-color: #f7f7f8;
    }

    /* 隐藏 Streamlit 默认元素 */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}

    /* ========== 侧边栏 ========== */
    section[data-testid="stSidebar"] {
        background-color: #1a1a2e;
    }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown h1,
    section[data-testid="stSidebar"] .stMarkdown h2,
    section[data-testid="stSidebar"] .stMarkdown h3,
    section[data-testid="stSidebar"] .stMarkdown li,
    section[data-testid="stSidebar"] .stMarkdown span {
        color: #e0e0e0 !important;
    }
    section[data-testid="stSidebar"] .stButton > button {
        background-color: #4F46E5;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 500;
        width: 100%;
        transition: all 0.2s ease;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background-color: #4338ca;
        box-shadow: 0 2px 8px rgba(79, 70, 229, 0.4);
    }

    /* ========== 页面标题区 ========== */
    .doubao-header {
        text-align: center;
        padding: 30px 0 20px 0;
    }
    .doubao-header h1 {
        font-size: 1.6rem;
        font-weight: 600;
        color: #1a1a2e;
        margin: 0;
    }
    .doubao-header p {
        font-size: 0.9rem;
        color: #888;
        margin: 6px 0 0 0;
    }

    /* ========== 欢迎消息 ========== */
    .welcome-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 16px;
        padding: 30px 36px;
        margin: 20px auto 30px auto;
        max-width: 600px;
        color: white;
        box-shadow: 0 4px 20px rgba(102, 126, 234, 0.3);
    }
    .welcome-card h2 {
        color: white;
        margin: 0 0 12px 0;
        font-size: 1.4rem;
    }
    .welcome-card p {
        color: rgba(255,255,255,0.9);
        margin: 4px 0;
        font-size: 0.95rem;
    }
    .welcome-card .feature-tag {
        display: inline-block;
        background: rgba(255,255,255,0.2);
        padding: 4px 12px;
        border-radius: 20px;
        margin: 4px 4px 0 0;
        font-size: 0.85rem;
    }

    /* ========== 快捷操作 ========== */
    .quick-actions {
        display: flex;
        gap: 10px;
        justify-content: center;
        margin: 16px 0 24px 0;
        flex-wrap: wrap;
    }
    .quick-action-btn {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 10px 18px;
        font-size: 0.85rem;
        color: #374151;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .quick-action-btn:hover {
        border-color: #4F46E5;
        color: #4F46E5;
        box-shadow: 0 2px 8px rgba(79, 70, 229, 0.15);
    }

    /* ========== 消息气泡 ========== */
    .chat-msg {
        display: flex;
        gap: 12px;
        margin-bottom: 20px;
        animation: fadeIn 0.3s ease-out;
    }
    .chat-msg.user {
        flex-direction: row-reverse;
    }
    .chat-avatar {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
        flex-shrink: 0;
    }
    .chat-avatar.ai {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    .chat-avatar.human {
        background-color: #4F46E5;
        color: white;
    }
    .chat-bubble {
        max-width: 75%;
        padding: 12px 16px;
        border-radius: 16px;
        font-size: 0.9rem;
        line-height: 1.6;
        word-break: break-word;
    }
    .chat-bubble.ai {
        background-color: white;
        color: #1a1a2e;
        border: 1px solid #e5e7eb;
        border-top-left-radius: 4px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .chat-bubble.user {
        background-color: #4F46E5;
        color: white;
        border-top-right-radius: 4px;
    }
    .chat-bubble .timestamp {
        font-size: 0.75rem;
        color: #999;
        margin-top: 6px;
    }
    .chat-bubble.user .timestamp {
        color: rgba(255,255,255,0.7);
    }

    /* ========== Markdown 渲染 ========== */
    .chat-bubble.ai h1, .chat-bubble.ai h2, .chat-bubble.ai h3 {
        margin-top: 12px;
        margin-bottom: 6px;
    }
    .chat-bubble.ai code {
        background: #f3f4f6;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.85em;
    }
    .chat-bubble.ai pre {
        background: #1e1e1e;
        color: #d4d4d4;
        padding: 12px;
        border-radius: 8px;
        overflow-x: auto;
        font-size: 0.85em;
    }

    /* ========== 文件附件指示器 ========== */
    .file-indicator {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: #f0f0f0;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 0.8rem;
        color: #555;
        margin-bottom: 8px;
    }
    .file-indicator.user-file {
        background: rgba(255,255,255,0.2);
        color: white;
    }

    /* ========== 分析结果卡片 ========== */
    .result-section {
        background: white;
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
        border: 1px solid #e5e7eb;
    }
    .result-section h4 {
        margin: 0 0 8px 0;
        font-size: 0.95rem;
    }
    .risk-tag {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 500;
    }
    .risk-tag.high { background: #fef2f2; color: #dc2626; }
    .risk-tag.medium { background: #fffbeb; color: #d97706; }
    .risk-tag.low { background: #f0fdf4; color: #16a34a; }

    /* ========== 加载动画 ========== */
    .typing-indicator {
        display: flex;
        gap: 4px;
        padding: 8px 12px;
    }
    .typing-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #999;
        animation: typingBounce 1.4s infinite ease-in-out;
    }
    .typing-dot:nth-child(1) { animation-delay: 0s; }
    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }

    @keyframes typingBounce {
        0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
        40% { transform: scale(1); opacity: 1; }
    }

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
    }

    /* ========== 输入区域优化 ========== */
    .stChatInput {
        border-radius: 12px !important;
    }

    /* ========== 按钮样式 ========== */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0,0,0,0.12);
    }

    /* ========== 分隔线 ========== */
    hr {
        border: none;
        border-top: 1px solid #e5e7eb;
        margin: 16px 0;
    }

    /* ========== Streamlit chat message 覆盖 ========== */
    [data-testid="stChatMessage"] {
        border-radius: 12px !important;
        padding: 8px 16px !important;
        margin-bottom: 8px !important;
    }

    /* ========== 历史记录会话项 ========== */
    .session-item {
        padding: 8px 12px;
        border-radius: 8px;
        margin-bottom: 4px;
        cursor: pointer;
        transition: background-color 0.2s;
        color: #ccc;
        font-size: 0.85rem;
    }
    .session-item:hover {
        background-color: rgba(255,255,255,0.1);
    }
    .session-item.active {
        background-color: rgba(79, 70, 229, 0.3);
        color: white;
    }

    /* ========== 隐藏元素 ========== */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
    }
    </style>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
