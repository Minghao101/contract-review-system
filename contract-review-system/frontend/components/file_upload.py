"""
文件上传组件 - 支持PDF/DOCX/TXT文件上传，通过FastAPI后端审查
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

API_BASE_URL = "http://localhost:8001/api/v1"


def render_file_upload():
    """渲染文件上传界面"""
    st.subheader("📄 上传合同文件")

    st.markdown("""
    支持的文件格式：
    - **TXT** - 纯文本合同
    - **PDF** - PDF格式合同
    - **DOCX** - Word文档合同
    """)

    # 文件上传
    uploaded_file = st.file_uploader(
        "选择合同文件",
        type=["txt", "pdf", "docx"],
        help="上传合同文件进行自动审查",
        key="file_uploader"
    )

    if uploaded_file is not None:
        # 显示文件信息
        file_details = {
            "文件名": uploaded_file.name,
            "文件类型": uploaded_file.type,
            "文件大小": f"{uploaded_file.size / 1024:.1f} KB"
        }
        st.json(file_details)

        # 审查按钮
        if st.button("🔍 开始审查", use_container_width=True, key="start_review"):
            _upload_and_review(uploaded_file)

    # 手动输入
    st.markdown("---")
    st.subheader("✏️ 或直接粘贴合同文本")

    manual_text = st.text_area(
        "合同文本",
        height=200,
        placeholder="在此粘贴合同文本...",
        key="manual_input"
    )

    if manual_text:
        char_count = len(manual_text)
        st.caption(f"📊 字符数: {char_count}")

        if st.button("📋 审查此文本", use_container_width=True, key="review_manual"):
            _review_text(manual_text)


def _upload_and_review(uploaded_file):
    """上传文件到后端并审查"""
    with st.spinner("🔄 正在上传并审查文件..."):
        progress = st.progress(0, text="上传文件...")

        try:
            # 重置文件指针
            uploaded_file.seek(0)

            # 准备文件数据
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}

            progress.progress(20, text="发送到后端...")

            # 调用后端上传审查接口
            response = requests.post(
                f"{API_BASE_URL}/upload/sync",
                files=files,
                data={
                    "contract_type": "general",
                    "review_focus": ""
                },
                timeout=300
            )

            progress.progress(80, text="处理结果...")

            if response.status_code == 200:
                result = response.json()
                progress.progress(100, text="审查完成！")

                # 显示审查结果
                _display_review_result(result, uploaded_file.name)

                # 保存到历史记录
                if "review_history" not in st.session_state:
                    st.session_state["review_history"] = []
                st.session_state["review_history"].append({
                    "contract_name": uploaded_file.name,
                    "status": result.get("status", "completed"),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "result": result
                })
            else:
                error_msg = f"后端返回错误: {response.status_code} - {response.text}"
                logger.error(error_msg)
                st.error(f"❌ {error_msg}")

        except requests.exceptions.ConnectionError:
            st.error(
                "❌ 无法连接到后端服务\n\n"
                "请在另一个终端启动FastAPI服务：\n"
                "```\n.venv\\Scripts\\python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8001\n```"
            )
        except Exception as e:
            logger.error(f"审查失败: {e}", exc_info=True)
            st.error(f"❌ 审查失败: {str(e)}")


def _review_text(contract_text: str):
    """审查文本内容"""
    with st.spinner("🔄 正在审查合同..."):
        progress = st.progress(0, text="提交审查...")

        try:
            progress.progress(20, text="发送到后端...")

            response = requests.post(
                f"{API_BASE_URL}/review/sync",
                json={
                    "contract_text": contract_text,
                    "contract_type": "general",
                    "review_focus": []
                },
                timeout=120
            )

            progress.progress(80, text="处理结果...")

            if response.status_code == 200:
                result = response.json()
                progress.progress(100, text="审查完成！")

                _display_review_result(result, "粘贴的合同文本")

                # 保存到历史记录
                if "review_history" not in st.session_state:
                    st.session_state["review_history"] = []
                st.session_state["review_history"].append({
                    "contract_name": contract_text[:30] + "...",
                    "status": result.get("status", "completed"),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "result": result
                })
            else:
                st.error(f"❌ 后端返回错误: {response.status_code}")

        except requests.exceptions.ConnectionError:
            st.error(
                "❌ 无法连接到后端服务\n\n"
                "请在另一个终端启动FastAPI服务：\n"
                "```\n.venv\\Scripts\\python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8001\n```"
            )
        except Exception as e:
            logger.error(f"审查失败: {e}", exc_info=True)
            st.error(f"❌ 审查失败: {str(e)}")


def _display_review_result(result: dict, filename: str):
    """显示审查结果"""
    st.markdown("---")
    st.subheader(f"📋 审查结果 - {filename}")

    # 状态
    status = result.get("status", "unknown")
    status_emoji = {"completed": "✅", "failed": "❌", "partial": "⚠️", "partial_failed": "⚠️"}.get(status, "❓")
    st.markdown(f"**审查状态**: {status_emoji} {status}")

    # 执行计划
    steps = result.get("execution_plan", result.get("steps_completed", []))
    if steps:
        with st.expander("📝 执行步骤", expanded=False):
            for step in steps:
                st.markdown(f"- ✅ {step}")

    # 文档解析结果 - 后端返回 document_info 在顶层
    if result.get("document_info"):
        info = result["document_info"]
        with st.expander("📄 文档解析", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**合同类型**: {info.get('contract_type', '未知')}")
            with col2:
                if info.get("basic_info"):
                    bi = info["basic_info"]
                    if bi.get("parties"):
                        st.markdown(f"**当事方**: {', '.join(bi['parties'])}")
                    if bi.get("title"):
                        st.markdown(f"**标题**: {bi['title']}")

            if info.get("sections_count"):
                st.markdown(f"**条款数量**: {info['sections_count']}")
            if info.get("text_length"):
                st.markdown(f"**文本长度**: {info['text_length']} 字符")

    # 条款分析 - 后端返回 sections 在顶层
    if result.get("sections"):
        sections = result["sections"]
        if isinstance(sections, list) and sections:
            with st.expander("📝 条款分析", expanded=True):
                for s in sections[:5]:
                    title = s.get("title", s.get("id", "条款"))
                    content = s.get("content", "")[:100]
                    st.markdown(f"- **{title}**: {content}")

    # 风险评估 - 后端返回 risks 在顶层
    if result.get("risks"):
        with st.expander("⚠️ 风险评估", expanded=True):
            for r in result["risks"]:
                level = r.get("level", r.get("severity", "medium"))
                emoji = {"high": "🔴", "critical": "🔴", "medium": "🟡", "low": "🟢"}.get(level, "⚪")
                title = r.get("title", r.get("name", "风险"))
                st.markdown(f"- {emoji} **{title}**")
                if r.get("description"):
                    st.markdown(f"  {r['description'][:100]}")

    # 风险等级
    if result.get("risk_level") and result["risk_level"] != "unknown":
        st.markdown(f"**整体风险等级**: {result['risk_level']}")

    # 合规检查 - 后端返回 compliance_violations 在顶层
    if result.get("compliance_violations"):
        with st.expander("✅ 合规检查", expanded=True):
            for v in result["compliance_violations"]:
                st.markdown(f"- ⚠️ {v.get('description', v.get('issue', str(v)))}")

    if result.get("compliance_status") and result["compliance_status"] != "unknown":
        score = result.get("compliance_score", "未知")
        st.markdown(f"**合规状态**: {result['compliance_status']} (得分: {score})")

    # 缺失条款
    if result.get("missing_clauses"):
        with st.expander("📋 缺失条款", expanded=False):
            for c in result["missing_clauses"]:
                st.markdown(f"- ❌ {c}")

    # 综合报告 - 后端返回 summary 在顶层
    if result.get("summary"):
        with st.expander("📊 综合报告", expanded=False):
            summary = result["summary"]
            if isinstance(summary, str):
                st.markdown(summary)
            elif isinstance(summary, dict):
                if summary.get("text"):
                    st.markdown(summary["text"])
                elif summary.get("content"):
                    st.markdown(summary["content"])
                else:
                    st.json(summary)

    if result.get("report"):
        with st.expander("📊 详细报告", expanded=False):
            report = result["report"]
            if isinstance(report, str):
                st.markdown(report)
            elif isinstance(report, dict):
                st.json(report)

    # 建议
    if result.get("recommendations"):
        with st.expander("💡 建议", expanded=False):
            for rec in result["recommendations"]:
                if isinstance(rec, str):
                    st.markdown(f"- {rec}")
                elif isinstance(rec, dict):
                    st.markdown(f"- {rec.get('title', rec.get('description', str(rec)))}")

    # 错误信息
    if result.get("error"):
        st.warning(f"⚠️ 注意: {result['error']}")

    # 耗时
    if result.get("elapsed_seconds"):
        st.caption(f"⏱️ 耗时: {result['elapsed_seconds']:.2f} 秒")
