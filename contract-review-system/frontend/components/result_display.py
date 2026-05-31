"""
结果展示组件 - 结构化审查结果展示模板

提供丰富的结果展示功能：
- 结构化结果卡片（文档解析、条款分析、风险评估、合规检查、报告生成）
- 交互式展开/折叠面板
- 风险等级可视化（颜色编码、图标）
- 指标卡片展示
- 审查流程时间线
- 结果导出功能
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st


# ============================================================
# 结果卡片模板（Result Cards）
# ============================================================

def render_result_card(title: str, content: str, icon: str = "📋",
                       status: str = "success", expanded: bool = True):
    """
    渲染通用结果卡片

    Args:
        title: 卡片标题
        content: 卡片内容（Markdown格式）
        icon: 卡片图标
        status: 状态 (success/warning/error/info)
        expanded: 是否默认展开
    """
    color_map = {
        "success": "#c8e6c9",
        "warning": "#fff3e0",
        "error": "#ffcdd2",
        "info": "#e3f2fd",
    }
    border_map = {
        "success": "#4caf50",
        "warning": "#ff9800",
        "error": "#f44336",
        "info": "#2196f3",
    }

    bg_color = color_map.get(status, color_map["info"])
    border_color = border_map.get(status, border_map["info"])

    card_html = f"""
    <div style="border-left: 4px solid {border_color};
                background-color: {bg_color};
                border-radius: 8px;
                padding: 12px 16px;
                margin-bottom: 12px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
        <div style="font-size: 1.1em; font-weight: bold; margin-bottom: 8px;">
            {icon} {title}
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)
    with st.expander(f"{icon} {title}", expanded=expanded):
        st.markdown(content)


def render_metric_card(label: str, value: str, delta: str = "",
                       icon: str = ""):
    """
    渲染指标卡片

    Args:
        label: 指标标签
        value: 指标值
        delta: 变化量（可选）
        icon: 图标（可选）
    """
    display_label = f"{icon} {label}" if icon else label
    st.metric(label=display_label, value=value, delta=delta or None)


# ============================================================
# 文档解析结果展示
# ============================================================

def render_parse_result(parse_data: Dict[str, Any]):
    """
    渲染文档解析结果

    Args:
        parse_data: 文档解析结果数据
    """
    st.markdown("### 📄 文档解析结果")

    doc_info = parse_data.get("document_info", {})

    # 指标卡片行
    col1, col2, col3 = st.columns(3)
    with col1:
        render_metric_card("合同类型", doc_info.get("type", "未知"), icon="📝")
    with col2:
        render_metric_card("甲方", _truncate(doc_info.get("party_a", "未知"), 15), icon="🏢")
    with col3:
        render_metric_card("乙方", _truncate(doc_info.get("party_b", "未知"), 15), icon="🏢")

    # 合同金额和期限
    amount = doc_info.get("amount", {})
    if amount:
        col4, col5 = st.columns(2)
        with col4:
            render_metric_card("合同金额",
                               amount.get("value", "未知"),
                               icon="💰")
        with col5:
            date_range = doc_info.get("date_range", {})
            render_metric_card("合同期限",
                               f"{date_range.get('start', '未知')} ~ {date_range.get('end', '未知')}",
                               icon="📅")

    # 关键条款列表
    key_clauses = parse_data.get("key_clauses", [])
    if key_clauses:
        st.markdown("#### 📋 关键条款")
        for clause in key_clauses[:8]:
            clause_title = clause.get("title", "条款")
            clause_summary = clause.get("summary", "")[:120]
            st.markdown(f"- **{clause_title}**: {clause_summary}")

    # 提取元数据
    metadata = parse_data.get("metadata", {})
    if metadata:
        with st.expander("📊 提取元数据", expanded=False):
            meta_cols = st.columns(3)
            with meta_cols[0]:
                st.caption(f"文本长度: {metadata.get('text_length', 'N/A')}")
            with meta_cols[1]:
                st.caption(f"段落数: {metadata.get('paragraph_count', 'N/A')}")
            with meta_cols[2]:
                st.caption(f"提取时间: {metadata.get('extraction_time', 'N/A')}s")


# ============================================================
# 条款分析结果展示
# ============================================================

def render_clause_result(clause_data: Dict[str, Any]):
    """
    渲染条款分析结果

    Args:
        clause_data: 条款分析结果数据
    """
    st.markdown("### 📝 条款分析结果")

    clauses = clause_data.get("clauses", [])
    if not clauses:
        st.info("未检测到具体条款信息。")
        return

    # 条款统计
    total = len(clauses)
    important = sum(1 for c in clauses if c.get("importance") == "high")
    col1, col2, col3 = st.columns(3)
    with col1:
        render_metric_card("条款总数", str(total), icon="📄")
    with col2:
        render_metric_card("重要条款", str(important), icon="⭐")
    with col3:
        render_metric_card("分析完成", "✅", icon="🔍")

    # 条款详情
    for i, clause in enumerate(clauses[:10], 1):
        title = clause.get("title", f"条款 {i}")
        summary = clause.get("summary", "")
        importance = clause.get("importance", "medium")
        risk_level = clause.get("risk_level", "low")

        importance_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(importance, "⚪")
        risk_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk_level, "⚪")

        with st.expander(f"{importance_icon} {title} | 重要性: {importance} | 风险: {risk_level}",
                         expanded=(importance == "high")):
            st.markdown(f"**摘要**: {summary}")
            if clause.get("key_points"):
                st.markdown("**要点**:")
                for point in clause["key_points"]:
                    st.markdown(f"  - {point}")
            if clause.get("obligations"):
                st.markdown("**义务**:")
                for obligation in clause["obligations"]:
                    st.markdown(f"  - {obligation}")


# ============================================================
# 风险评估结果展示
# ============================================================

def render_risk_result(risk_data: Dict[str, Any]):
    """
    渲染风险评估结果

    Args:
        risk_data: 风险评估结果数据
    """
    st.markdown("### ⚠️ 风险评估结果")

    risks = risk_data.get("risks", [])
    if not risks:
        st.success("✅ 未发现明显风险。")
        return

    # 风险统计
    high_count = sum(1 for r in risks if r.get("level") == "high")
    medium_count = sum(1 for r in risks if r.get("level") == "medium")
    low_count = sum(1 for r in risks if r.get("level") == "low")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_metric_card("风险总数", str(len(risks)), icon="⚠️")
    with col2:
        render_metric_card("高风险", str(high_count), icon="🔴")
    with col3:
        render_metric_card("中风险", str(medium_count), icon="🟡")
    with col4:
        render_metric_card("低风险", str(low_count), icon="🟢")

    # 风险等级分布可视化
    if risks:
        _render_risk_distribution_chart(high_count, medium_count, low_count)

    # 风险详情列表
    st.markdown("#### 📋 风险详情")
    for i, risk in enumerate(risks, 1):
        level = risk.get("level", "medium")
        title = risk.get("title", f"风险 {i}")
        description = risk.get("description", "")
        suggestion = risk.get("suggestion", "")

        level_config = {
            "high": ("🔴 高风险", "error"),
            "medium": ("🟡 中风险", "warning"),
            "low": ("🟢 低风险", "success"),
        }
        level_label, card_status = level_config.get(level, ("⚪ 未知", "info"))

        card_content = f"**等级**: {level_label}\n\n"
        card_content += f"**描述**: {description}\n\n"
        if suggestion:
            card_content += f"**建议**: {suggestion}\n\n"
        if risk.get("clause"):
            card_content += f"**相关条款**: {risk['clause']}\n"

        render_result_card(
            title=f"风险 {i}: {title}",
            content=card_content,
            icon="⚠️" if level == "high" else ("⚡" if level == "medium" else "💡"),
            status=card_status,
            expanded=(level == "high")
        )

    # 缓解建议汇总
    suggestions = [r.get("suggestion", "") for r in risks if r.get("suggestion")]
    if suggestions:
        st.markdown("#### 💡 缓解建议汇总")
        for i, suggestion in enumerate(suggestions, 1):
            st.markdown(f"{i}. {suggestion}")


def _render_risk_distribution_chart(high: int, medium: int, low: int):
    """渲染风险分布图（使用Streamlit原生组件）"""
    total = high + medium + low
    if total == 0:
        return

    st.markdown("#### 📊 风险分布")

    # 使用进度条模拟饼图
    bar_html = f"""
    <div style="display: flex; height: 24px; border-radius: 12px; overflow: hidden;
                margin-bottom: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
        <div style="width: {high/total*100:.1f}%; background-color: #f44336;
                    display: flex; align-items: center; justify-content: center;
                    color: white; font-size: 12px; font-weight: bold;">
            {"🔴 " + str(high) if high > 0 else ""}
        </div>
        <div style="width: {medium/total*100:.1f}%; background-color: #ff9800;
                    display: flex; align-items: center; justify-content: center;
                    color: white; font-size: 12px; font-weight: bold;">
            {"🟡 " + str(medium) if medium > 0 else ""}
        </div>
        <div style="width: {low/total*100:.1f}%; background-color: #4caf50;
                    display: flex; align-items: center; justify-content: center;
                    color: white; font-size: 12px; font-weight: bold;">
            {"🟢 " + str(low) if low > 0 else ""}
        </div>
    </div>
    <div style="display: flex; justify-content: space-between; font-size: 12px; color: #666;">
        <span>🔴 高风险: {high} ({high/total*100:.0f}%)</span>
        <span>🟡 中风险: {medium} ({medium/total*100:.0f}%)</span>
        <span>🟢 低风险: {low} ({low/total*100:.0f}%)</span>
    </div>
    """
    st.markdown(bar_html, unsafe_allow_html=True)


# ============================================================
# 合规检查结果展示
# ============================================================

def render_compliance_result(compliance_data: Dict[str, Any]):
    """
    渲染合规检查结果

    Args:
        compliance_data: 合规检查结果数据
    """
    st.markdown("### ✅ 合规检查结果")

    issues = compliance_data.get("issues", [])
    passed = compliance_data.get("passed_checks", [])
    score = compliance_data.get("compliance_score", None)

    # 合规评分
    if score is not None:
        score_color = "green" if score >= 80 else ("orange" if score >= 60 else "red")
        render_metric_card("合规评分", f"{score}/100", icon="📊")
        st.progress(score / 100)

    # 检查统计
    col1, col2 = st.columns(2)
    with col1:
        render_metric_card("通过项", str(len(passed)), icon="✅")
    with col2:
        render_metric_card("问题项", str(len(issues)), icon="⚠️")

    # 合规问题详情
    if issues:
        st.markdown("#### ⚠️ 合规问题")
        for i, issue in enumerate(issues, 1):
            severity = issue.get("severity", "warning")
            regulation = issue.get("regulation", "")
            description = issue.get("description", "")

            severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(severity, "⚠️")

            with st.expander(f"{severity_icon} 问题 {i}: {description[:60]}",
                             expanded=(severity == "high")):
                st.markdown(f"**描述**: {description}")
                if regulation:
                    st.markdown(f"**相关法规**: {regulation}")
                if issue.get("suggestion"):
                    st.markdown(f"**修改建议**: {issue['suggestion']}")
    else:
        st.success("✅ 未发现合规问题，所有检查项均通过。")

    # 通过的检查项
    if passed:
        with st.expander(f"✅ 已通过的检查项 ({len(passed)} 项)", expanded=False):
            for check in passed:
                st.markdown(f"- ✅ {check}")


# ============================================================
# 报告生成结果展示
# ============================================================

def render_report_result(report_data: Dict[str, Any]):
    """
    渲染报告生成结果

    Args:
        report_data: 报告生成结果数据
    """
    st.markdown("### 📊 综合审查报告")

    # 报告概要
    summary = report_data.get("summary", "")
    if summary:
        with st.expander("📝 报告概要", expanded=True):
            st.markdown(summary)

    # 各维度评估
    dimensions = report_data.get("dimensions", [])
    if dimensions:
        st.markdown("#### 📋 各维度评估")
        for dim in dimensions:
            dim_name = dim.get("name", "维度")
            dim_score = dim.get("score", 0)
            dim_comment = dim.get("comment", "")

            st.markdown(f"**{dim_name}**")
            st.progress(dim_score / 100)
            st.caption(f"评分: {dim_score}/100 - {dim_comment}")

    # 建议列表
    recommendations = report_data.get("recommendations", [])
    if recommendations:
        st.markdown("#### 💡 改进建议")
        for i, rec in enumerate(recommendations, 1):
            priority = rec.get("priority", "medium")
            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
            st.markdown(f"{i}. {priority_icon} **{rec.get('title', '建议')}**: "
                       f"{rec.get('description', '')}")

    # 总体评分
    overall_score = report_data.get("overall_score")
    if overall_score is not None:
        st.markdown("#### 🏆 总体评分")
        score_color = "green" if overall_score >= 80 else ("orange" if overall_score >= 60 else "red")
        st.markdown(f"### :{score_color}[{overall_score}/100]")


# ============================================================
# 审查流程时间线
# ============================================================

def render_review_timeline(steps: List[Dict[str, Any]]):
    """
    渲染审查流程时间线

    Args:
        steps: 步骤列表，每个步骤包含 name, status, duration, agent 等字段
    """
    if not steps:
        return

    st.markdown("### 🔄 审查流程")

    timeline_html = '<div style="padding: 10px 0;">'
    for i, step in enumerate(steps):
        name = step.get("name", f"步骤 {i+1}")
        status = step.get("status", "pending")
        duration = step.get("duration", "")
        agent = step.get("agent", "")

        status_config = {
            "completed": ("✅", "#4caf50"),
            "running": ("🔄", "#2196f3"),
            "failed": ("❌", "#f44336"),
            "pending": ("⏳", "#9e9e9e"),
        }
        icon, color = status_config.get(status, ("❓", "#9e9e9e"))

        timeline_html += f"""
        <div style="display: flex; align-items: center; padding: 6px 0;
                    border-left: 3px solid {color}; margin-left: 10px;
                    padding-left: 15px; margin-bottom: 4px;">
            <span style="margin-right: 10px; font-size: 16px;">{icon}</span>
            <div style="flex: 1;">
                <strong style="color: {color};">{name}</strong>
                {f'<span style="color: #666; margin-left: 8px;">({agent})</span>' if agent else ''}
            </div>
            {f'<span style="color: #999; font-size: 12px;">{duration}</span>' if duration else ''}
        </div>
        """
    timeline_html += "</div>"

    st.markdown(timeline_html, unsafe_allow_html=True)


# ============================================================
# 完整审查结果展示
# ============================================================

def render_full_review_result(result: Dict[str, Any], contract_text: str = ""):
    """
    渲染完整的审查结果

    Args:
        result: 完整的审查结果字典
        contract_text: 合同文本（可选，用于显示摘要）
    """
    # 审查状态头
    status = result.get("status", "unknown")
    status_config = {
        "completed": ("✅ 审查完成", "success"),
        "failed": ("❌ 审查失败", "error"),
        "partial": ("⚠️ 部分完成", "warning"),
    }
    status_label, status_type = status_config.get(status, ("❓ 未知", "info"))

    header_html = f"""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white; padding: 20px; border-radius: 12px;
                margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <h2 style="margin: 0; color: white;">📋 合同审查报告</h2>
        <p style="margin: 5px 0 0 0; opacity: 0.9;">{status_label} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

    # 合同摘要
    if contract_text:
        with st.expander("📄 合同摘要", expanded=False):
            st.text(contract_text[:500] + ("..." if len(contract_text) > 500 else ""))

    # 审查流程时间线
    steps = result.get("steps", [])
    if steps:
        render_review_timeline(steps)

    # 各阶段结果
    if result.get("parse_result"):
        render_parse_result(result["parse_result"])

    if result.get("clause_result"):
        render_clause_result(result["clause_result"])

    if result.get("risk_result"):
        render_risk_result(result["risk_result"])

    if result.get("compliance_result"):
        render_compliance_result(result["compliance_result"])

    if result.get("report_result"):
        render_report_result(result["report_result"])

    # 错误信息
    if result.get("error"):
        st.error(f"⚠️ 审查过程中遇到问题: {result['error']}")

    # 底部操作栏
    _render_result_actions(result)


def _render_result_actions(result: Dict[str, Any]):
    """渲染结果底部操作栏"""
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📋 复制报告摘要", use_container_width=True):
            summary = _generate_text_summary(result)
            st.code(summary, language=None)
            st.success("报告摘要已生成！")
    with col2:
        if st.button("📊 导出JSON", use_container_width=True):
            import json
            st.code(json.dumps(result, ensure_ascii=False, indent=2)[:2000],
                    language="json")
    with col3:
        if st.button("🔄 重新审查", use_container_width=True):
            st.session_state.pop("last_result", None)
            st.rerun()


def _generate_text_summary(result: Dict[str, Any]) -> str:
    """生成纯文本摘要"""
    lines = ["=== 合同审查报告摘要 ===\n"]

    status = result.get("status", "unknown")
    lines.append(f"审查状态: {status}")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 文档信息
    parse = result.get("parse_result", {})
    doc_info = parse.get("document_info", {})
    if doc_info:
        lines.append("--- 文档信息 ---")
        lines.append(f"合同类型: {doc_info.get('type', '未知')}")
        lines.append(f"甲方: {doc_info.get('party_a', '未知')}")
        lines.append(f"乙方: {doc_info.get('party_b', '未知')}")
        lines.append("")

    # 风险摘要
    risk = result.get("risk_result", {})
    risks = risk.get("risks", [])
    if risks:
        lines.append(f"--- 风险评估 ({len(risks)} 项) ---")
        for r in risks:
            level = r.get("level", "medium")
            lines.append(f"[{level.upper()}] {r.get('title', '风险')}: "
                        f"{r.get('description', '')[:80]}")
        lines.append("")

    # 合规摘要
    compliance = result.get("compliance_result", {})
    issues = compliance.get("issues", [])
    if issues:
        lines.append(f"--- 合规问题 ({len(issues)} 项) ---")
        for issue in issues:
            lines.append(f"- {issue.get('description', '')[:80]}")

    return "\n".join(lines)


# ============================================================
# 快速结果展示（用于多轮对话中的追问）
# ============================================================

def render_quick_risk_result(risk_data: Dict[str, Any]):
    """渲染快速风险评估结果（简化版）"""
    st.markdown("#### ⚠️ 快速风险评估")

    risks = risk_data.get("risks", [])
    if not risks:
        st.success("未发现明显风险。")
        return

    for risk in risks[:5]:
        level = risk.get("level", "medium")
        emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(level, "⚪")
        st.markdown(f"- {emoji} **{risk.get('title', '风险')}**: "
                   f"{risk.get('description', '')[:150]}")


def render_quick_summary(result: Dict[str, Any]) -> str:
    """生成快速摘要文本（用于聊天消息）"""
    status = result.get("status", "unknown")
    status_emoji = {"completed": "✅", "failed": "❌", "partial": "⚠️"}.get(status, "❓")

    parts = [f"**审查状态**: {status_emoji} {status}\n"]

    # 统计信息
    risk_result = result.get("risk_result", {})
    risks = risk_result.get("risks", [])
    high_risks = sum(1 for r in risks if r.get("level") == "high")

    if risks:
        risk_text = f"**风险**: 发现 {len(risks)} 项"
        if high_risks:
            risk_text += f"（其中 {high_risks} 项高风险）"
        parts.append(risk_text)

    compliance = result.get("compliance_result", {})
    issues = compliance.get("issues", [])
    if issues:
        parts.append(f"**合规**: {len(issues)} 项问题")

    return "\n".join(parts)


# ============================================================
# 辅助函数
# ============================================================

def _truncate(text: str, max_length: int = 20) -> str:
    """截断文本"""
    if not text:
        return "未知"
    return text[:max_length] + ("..." if len(text) > max_length else "")


def render_review_result(record: dict):
    """
    渲染审查结果记录（兼容旧接口）

    Args:
        record: 审查结果记录
    """
    status = record.get("status", "unknown")
    result = record.get("result", {})

    # 状态标签
    status_config = {
        "completed": ("✅ 完成", "status-completed"),
        "failed": ("❌ 失败", "status-failed"),
        "partial": ("⚠️ 部分完成", "status-processing"),
    }
    label, css_class = status_config.get(status, ("❓ 未知", ""))

    st.markdown(f'<span class="status-badge {css_class}">{label}</span>',
                unsafe_allow_html=True)

    st.markdown(f"**时间**: {record.get('timestamp', 'N/A')}")

    # 使用新的结构化展示
    if result.get("parse_result"):
        render_parse_result(result["parse_result"])

    if result.get("risk_result"):
        render_risk_result(result["risk_result"])

    if result.get("compliance_result"):
        render_compliance_result(result["compliance_result"])

    if result.get("report_result"):
        render_report_result(result["report_result"])
