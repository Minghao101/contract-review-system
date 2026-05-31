"""
进度追踪组件 - 加载动画和进度显示

提供丰富的进度展示功能：
- 多步骤进度追踪器
- Agent执行状态实时显示
- 动画加载指示器
- 阶段性进度条
- 耗时统计
"""
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st


# ============================================================
# 审查步骤定义
# ============================================================

REVIEW_STEPS = [
    {"id": "init", "name": "初始化", "icon": "🚀", "description": "初始化审查环境"},
    {"id": "parse", "name": "文档解析", "icon": "📄", "description": "解析合同文档"},
    {"id": "clause", "name": "条款分析", "icon": "📝", "description": "分析合同条款"},
    {"id": "risk", "name": "风险评估", "icon": "⚠️", "description": "评估合同风险"},
    {"id": "compliance", "name": "合规检查", "icon": "✅", "description": "检查合规性"},
    {"id": "report", "name": "报告生成", "icon": "📊", "description": "生成审查报告"},
    {"id": "complete", "name": "完成", "icon": "🎉", "description": "审查完成"},
]


# ============================================================
# 多步骤进度追踪器
# ============================================================

class ReviewProgressTracker:
    """
    审查进度追踪器

    管理审查过程中的步骤状态、耗时和进度百分比。
    """

    def __init__(self, steps: Optional[List[Dict[str, Any]]] = None):
        """
        初始化进度追踪器

        Args:
            steps: 自定义步骤列表，None 则使用默认 REVIEW_STEPS
        """
        self.steps = steps if steps is not None else REVIEW_STEPS.copy()
        self.current_step_index = 0
        self.step_states: Dict[str, Dict[str, Any]] = {}
        self.start_time = time.time()
        self.end_time: Optional[float] = None

        # 初始化所有步骤状态
        for i, step in enumerate(self.steps):
            self.step_states[step["id"]] = {
                "status": "pending",  # pending / running / completed / failed
                "start_time": None,
                "end_time": None,
                "duration": None,
                "progress": 0,
                "message": "",
            }

    def start_step(self, step_id: str, message: str = ""):
        """
        开始一个步骤

        Args:
            step_id: 步骤ID
            message: 状态消息
        """
        if step_id in self.step_states:
            self.step_states[step_id]["status"] = "running"
            self.step_states[step_id]["start_time"] = time.time()
            self.step_states[step_id]["message"] = message
            # 将之前的步骤标记为完成
            for sid, state in self.step_states.items():
                if sid != step_id and state["status"] == "pending":
                    break
                if state["status"] == "running" and sid != step_id:
                    self.complete_step(sid)

    def complete_step(self, step_id: str, message: str = ""):
        """
        完成一个步骤

        Args:
            step_id: 步骤ID
            message: 完成消息
        """
        if step_id in self.step_states:
            now = time.time()
            state = self.step_states[step_id]
            state["status"] = "completed"
            state["end_time"] = now
            state["progress"] = 100
            state["message"] = message
            if state["start_time"]:
                state["duration"] = now - state["start_time"]

    def fail_step(self, step_id: str, message: str = ""):
        """
        标记步骤失败

        Args:
            step_id: 步骤ID
            message: 错误消息
        """
        if step_id in self.step_states:
            now = time.time()
            state = self.step_states[step_id]
            state["status"] = "failed"
            state["end_time"] = now
            state["message"] = message
            if state["start_time"]:
                state["duration"] = now - state["start_time"]

    def update_progress(self, step_id: str, progress: int, message: str = ""):
        """
        更新步骤进度

        Args:
            step_id: 步骤ID
            progress: 进度百分比 (0-100)
            message: 状态消息
        """
        if step_id in self.step_states:
            self.step_states[step_id]["progress"] = min(100, max(0, progress))
            if message:
                self.step_states[step_id]["message"] = message

    def finish(self):
        """完成整个审查"""
        self.end_time = time.time()
        # 完成所有未完成的步骤
        for step_id, state in self.step_states.items():
            if state["status"] in ("pending", "running"):
                self.complete_step(step_id)

    def get_overall_progress(self) -> int:
        """获取总体进度百分比"""
        if not self.steps:
            return 0
        total = 0
        for step in self.steps:
            state = self.step_states.get(step["id"], {})
            total += state.get("progress", 0)
        return total // len(self.steps) if self.steps else 0

    def get_total_duration(self) -> float:
        """获取总耗时（秒）"""
        end = self.end_time or time.time()
        return end - self.start_time

    def get_step_duration(self, step_id: str) -> Optional[float]:
        """获取单步骤耗时"""
        state = self.step_states.get(step_id, {})
        return state.get("duration")

    def get_status_summary(self) -> Dict[str, Any]:
        """获取状态摘要"""
        completed = sum(1 for s in self.step_states.values() if s["status"] == "completed")
        failed = sum(1 for s in self.step_states.values() if s["status"] == "failed")
        running = sum(1 for s in self.step_states.values() if s["status"] == "running")
        total = len(self.steps)

        return {
            "total_steps": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "overall_progress": self.get_overall_progress(),
            "total_duration": round(self.get_total_duration(), 2),
            "is_complete": completed + failed >= total,
        }

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "steps": [
                {
                    **step,
                    **self.step_states.get(step["id"], {}),
                }
                for step in self.steps
            ],
            "overall_progress": self.get_overall_progress(),
            "total_duration": round(self.get_total_duration(), 2),
            "status_summary": self.get_status_summary(),
        }


# ============================================================
# 进度追踪器UI渲染
# ============================================================

def render_progress_tracker(tracker: ReviewProgressTracker):
    """
    渲染进度追踪器UI

    Args:
        tracker: ReviewProgressTracker 实例
    """
    # 总体进度条
    overall = tracker.get_overall_progress()
    summary = tracker.get_status_summary()

    # 进度头部
    header_html = f"""
    <div style="display: flex; justify-content: space-between; align-items: center;
                margin-bottom: 8px;">
        <span style="font-weight: bold; font-size: 14px;">
            🔄 审查进度 ({summary['completed']}/{summary['total_steps']} 步骤完成)
        </span>
        <span style="color: #666; font-size: 13px;">
            ⏱️ {summary['total_duration']:.1f}s
        </span>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)
    st.progress(overall / 100, text=f"总体进度: {overall}%")

    # 步骤详情
    for step in tracker.steps:
        state = tracker.step_states.get(step["id"], {})
        status = state.get("status", "pending")
        progress = state.get("progress", 0)
        message = state.get("message", "")
        duration = state.get("duration")

        # 状态图标
        status_icons = {
            "completed": "✅",
            "running": "🔄",
            "failed": "❌",
            "pending": "⏳",
        }
        icon = status_icons.get(status, "❓")

        # 步骤HTML
        step_html = f"""
        <div style="display: flex; align-items: center; padding: 4px 0;
                    font-size: 13px; color: {'#333' if status != 'pending' else '#999'};">
            <span style="width: 24px; text-align: center;">{icon}</span>
            <span style="width: 24px; text-align: center;">{step['icon']}</span>
            <span style="flex: 1; margin-left: 4px;">{step['name']}</span>
        """
        if duration is not None:
            step_html += f'<span style="color: #999; width: 60px; text-align: right;">{duration:.1f}s</span>'
        elif status == "running":
            step_html += '<span style="color: #2196f3; width: 60px; text-align: right;">进行中...</span>'
        else:
            step_html += '<span style="width: 60px;"></span>'

        step_html += "</div>"
        st.markdown(step_html, unsafe_allow_html=True)

        # 运行中的步骤显示进度条
        if status == "running" and progress > 0:
            st.progress(progress / 100, text=f"  {message or '处理中...'}")


def render_compact_progress(tracker: ReviewProgressTracker):
    """
    渲染紧凑型进度条（适用于聊天消息中）

    Args:
        tracker: ReviewProgressTracker 实例
    """
    overall = tracker.get_overall_progress()
    summary = tracker.get_status_summary()

    # 当前步骤
    current_step = ""
    for step in tracker.steps:
        state = tracker.step_states.get(step["id"], {})
        if state.get("status") == "running":
            current_step = f"{step['icon']} {step['name']}"
            break

    if not current_step and summary["is_complete"]:
        current_step = "🎉 完成"

    compact_html = f"""
    <div style="background: #f8f9fa; border-radius: 8px; padding: 10px 14px;
                margin: 4px 0; border: 1px solid #e9ecef;">
        <div style="display: flex; justify-content: space-between; align-items: center;
                    margin-bottom: 6px;">
            <span style="font-size: 13px; font-weight: 500;">
                {current_step or '⏳ 准备中...'}
            </span>
            <span style="font-size: 12px; color: #666;">
                {overall}% | {summary['total_duration']:.1f}s
            </span>
        </div>
        <div style="height: 6px; background: #e9ecef; border-radius: 3px; overflow: hidden;">
            <div style="height: 100%; width: {overall}%;
                        background: linear-gradient(90deg, #2196f3, #4caf50);
                        border-radius: 3px; transition: width 0.3s ease;">
            </div>
        </div>
    </div>
    """
    st.markdown(compact_html, unsafe_allow_html=True)


# ============================================================
# 加载动画组件
# ============================================================

def render_loading_spinner(message: str = "加载中...", style: str = "default"):
    """
    渲染加载动画

    Args:
        message: 加载提示文本
        style: 样式 (default/dots/pulse/wave)
    """
    if style == "dots":
        loading_html = f"""
        <div style="text-align: center; padding: 20px;">
            <div style="display: inline-flex; gap: 6px;">
                <div style="width: 10px; height: 10px; border-radius: 50%;
                            background: #2196f3; animation: bounce 1.4s infinite ease-in-out;
                            animation-delay: -0.32s;"></div>
                <div style="width: 10px; height: 10px; border-radius: 50%;
                            background: #2196f3; animation: bounce 1.4s infinite ease-in-out;
                            animation-delay: -0.16s;"></div>
                <div style="width: 10px; height: 10px; border-radius: 50%;
                            background: #2196f3; animation: bounce 1.4s infinite ease-in-out;"></div>
            </div>
            <p style="margin-top: 10px; color: #666; font-size: 14px;">{message}</p>
            <style>
            @keyframes bounce {{
                0%, 80%, 100% {{ transform: scale(0); }}
                40% {{ transform: scale(1.0); }}
            }}
            </style>
        </div>
        """
        st.markdown(loading_html, unsafe_allow_html=True)
    elif style == "pulse":
        loading_html = f"""
        <div style="text-align: center; padding: 20px;">
            <div style="width: 40px; height: 40px; border-radius: 50%;
                        background: #2196f3; margin: 0 auto;
                        animation: pulse 1.5s infinite;"></div>
            <p style="margin-top: 10px; color: #666; font-size: 14px;">{message}</p>
            <style>
            @keyframes pulse {{
                0% {{ transform: scale(0.8); opacity: 1; }}
                50% {{ transform: scale(1.2); opacity: 0.5; }}
                100% {{ transform: scale(0.8); opacity: 1; }}
            }}
            </style>
        </div>
        """
        st.markdown(loading_html, unsafe_allow_html=True)
    elif style == "wave":
        loading_html = f"""
        <div style="text-align: center; padding: 20px;">
            <div style="display: inline-flex; gap: 4px; align-items: end; height: 30px;">
                {[f'<div style="width: 4px; background: #2196f3; border-radius: 2px;'
                  f'animation: wave 1.2s infinite ease-in-out; animation-delay: {i*0.1}s;'
                  f'height: 10px;"></div>' for i in range(5)]}
            </div>
            <p style="margin-top: 10px; color: #666; font-size: 14px;">{message}</p>
            <style>
            @keyframes wave {{
                0%, 100% {{ height: 10px; }}
                50% {{ height: 30px; }}
            }}
            </style>
        </div>
        """
        st.markdown(loading_html, unsafe_allow_html=True)
    else:
        # 默认使用 Streamlit spinner
        return st.spinner(message)


def render_agent_status_card(agent_name: str, status: str, message: str = "",
                              icon: str = "🤖", duration: float = None):
    """
    渲染Agent状态卡片

    Args:
        agent_name: Agent名称
        status: 状态 (running/completed/failed/pending)
        message: 状态消息
        icon: Agent图标
        duration: 耗时（秒）
    """
    status_config = {
        "completed": ("✅ 完成", "#c8e6c9", "#2e7d32"),
        "running": ("🔄 运行中", "#e3f2fd", "#1565c0"),
        "failed": ("❌ 失败", "#ffcdd2", "#c62828"),
        "pending": ("⏳ 等待中", "#f5f5f5", "#757575"),
    }
    label, bg_color, text_color = status_config.get(status, ("❓ 未知", "#f5f5f5", "#333"))

    duration_text = f" | ⏱️ {duration:.1f}s" if duration else ""

    card_html = f"""
    <div style="display: flex; align-items: center; padding: 10px 14px;
                background: {bg_color}; border-radius: 8px;
                margin-bottom: 6px; border: 1px solid {text_color}20;">
        <span style="font-size: 20px; margin-right: 10px;">{icon}</span>
        <div style="flex: 1;">
            <div style="font-weight: bold; color: {text_color}; font-size: 14px;">
                {agent_name}
                <span style="font-size: 12px; margin-left: 8px; font-weight: normal;">
                    {label}{duration_text}
                </span>
            </div>
            {'<div style="font-size: 12px; color: #666; margin-top: 2px;">' + message + '</div>' if message else ''}
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)


# ============================================================
# 状态提示组件
# ============================================================

def render_status_message(status: str, title: str, detail: str = "",
                          actions: Optional[List[Dict[str, str]]] = None):
    """
    渲染状态提示消息

    Args:
        status: 状态类型 (success/warning/error/info)
        title: 标题
        detail: 详细信息
        actions: 操作按钮列表 [{"label": "按钮文本", "key": "按钮key"}]
    """
    type_config = {
        "success": ("✅", "#c8e6c9", "#2e7d32"),
        "warning": ("⚠️", "#fff3e0", "#e65100"),
        "error": ("❌", "#ffcdd2", "#c62828"),
        "info": ("ℹ️", "#e3f2fd", "#1565c0"),
    }
    icon, bg_color, text_color = type_config.get(status, type_config["info"])

    html = f"""
    <div style="background: {bg_color}; border-radius: 8px; padding: 14px 18px;
                border-left: 4px solid {text_color}; margin: 8px 0;">
        <div style="font-weight: bold; color: {text_color}; font-size: 15px;">
            {icon} {title}
        </div>
        {'<div style="color: #555; font-size: 13px; margin-top: 4px;">' + detail + '</div>' if detail else ''}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

    if actions:
        cols = st.columns(len(actions))
        for col, action in zip(cols, actions):
            with col:
                if st.button(action["label"], key=action.get("key", action["label"]),
                            use_container_width=True):
                    if action.get("callback"):
                        action["callback"]()


# ============================================================
# 实用函数
# ============================================================

def create_review_tracker() -> ReviewProgressTracker:
    """创建并返回审查进度追踪器"""
    return ReviewProgressTracker()


def format_duration(seconds: float) -> str:
    """
    格式化耗时显示

    Args:
        seconds: 秒数

    Returns:
        格式化的字符串
    """
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.0f}s"


def get_status_emoji(status: str) -> str:
    """获取状态对应的emoji"""
    return {
        "completed": "✅",
        "running": "🔄",
        "failed": "❌",
        "pending": "⏳",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌",
        "info": "ℹ️",
    }.get(status, "❓")
