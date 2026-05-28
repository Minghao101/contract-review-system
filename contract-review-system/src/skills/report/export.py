"""
导出Skill - 将报告导出为PDF/Word/HTML格式
"""
from typing import Any, Dict, Optional
import logging
import json

from ..base_skill import BaseSkill

logger = logging.getLogger(__name__)


class ExportSkill(BaseSkill):
    """
    导出Skill

    功能：
    - 将结构化报告导出为HTML格式
    - 将结构化报告导出为Markdown格式
    - 将结构化报告导出为JSON格式
    """

    def __init__(self):
        super().__init__(
            skill_id="export",
            name="报告导出",
            description="将审查报告导出为HTML/Markdown/JSON格式",
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        report_data = kwargs.get("report_data", {})
        export_format = kwargs.get("format", "html")

        try:
            if export_format == "html":
                content = self._export_html(report_data)
            elif export_format == "markdown":
                content = self._export_markdown(report_data)
            elif export_format == "json":
                content = json.dumps(report_data, ensure_ascii=False, indent=2)
            else:
                return {"error": f"不支持的格式: {export_format}"}

            return {
                "format": export_format,
                "content": content,
                "size": len(content),
            }
        except Exception as e:
            logger.error(f"报告导出失败: {e}")
            return {"error": str(e)}

    def _export_html(self, data: Dict) -> str:
        report = data.get("report", data)
        summary = data.get("summary", {})
        overall_score = data.get("overall_score", 0)

        risk_analysis = report.get("risk_analysis", {})
        compliance_analysis = report.get("compliance_analysis", {})
        clause_analysis = report.get("clause_analysis", {})
        recommendations = report.get("recommendations", [])
        conclusion = report.get("conclusion", {})
        executive_summary = report.get("executive_summary", "")

        verdict = conclusion.get("verdict", "需要人工审查")
        verdict_colors = {
            "建议签署": "#27ae60",
            "建议修改后签署": "#f39c12",
            "建议补充条款后签署": "#e67e22",
            "不建议签署": "#e74c3c",
        }
        verdict_color = verdict_colors.get(verdict, "#95a5a6")

        risk_level = risk_analysis.get("overall_level", "unknown")
        risk_level_cn = {"low": "低", "medium": "中等", "high": "高", "critical": "极高"}.get(risk_level, "未知")

        risk_rows = ""
        for r in risk_analysis.get("risks", []):
            severity = r.get("severity", "low")
            sev_colors = {"high": "#e74c3c", "medium": "#f39c12", "low": "#27ae60"}
            sev_color = sev_colors.get(severity, "#95a5a6")
            risk_rows += f"""<tr>
<td>{r.get('name', 'N/A')}</td>
<td><span style="color:{sev_color};font-weight:bold">{severity}</span></td>
<td>{r.get('description', '')}</td>
<td>{r.get('suggestion', '')}</td>
</tr>"""

        rec_items = ""
        for rec in recommendations:
            priority = rec.get("priority", "medium")
            p_colors = {"high": "#e74c3c", "medium": "#f39c12", "low": "#27ae60"}
            rec_items += f"""<div style="padding:8px 12px;margin:4px 0;border-left:4px solid {p_colors.get(priority,'#95a5a6')};background:#f8f9fa;border-radius:4px">
<strong>[{rec.get('category','')}]</strong> {rec.get('content','')}
</div>"""

        score_color = "#27ae60" if overall_score >= 80 else "#f39c12" if overall_score >= 60 else "#e74c3c"

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>合同审查报告</title>
<style>
body {{ font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; background: #f5f6fa; color: #2d3436; }}
.header {{ background: linear-gradient(135deg, #2c3e50, #3498db); color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
.header h1 {{ margin: 0 0 10px 0; }}
.header .meta {{ opacity: 0.8; font-size: 14px; }}
.score-badge {{ display: inline-block; padding: 8px 20px; border-radius: 20px; font-size: 24px; font-weight: bold; background: {score_color}; color: white; margin-top: 10px; }}
.verdict {{ display: inline-block; padding: 10px 24px; border-radius: 8px; font-size: 18px; font-weight: bold; background: {verdict_color}; color: white; }}
.section {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.section h2 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #eee; }}
th {{ background: #f8f9fa; font-weight: 600; }}
.stat-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
.stat-card {{ text-align: center; padding: 16px; border-radius: 8px; background: #f8f9fa; }}
.stat-card .value {{ font-size: 28px; font-weight: bold; color: #2c3e50; }}
.stat-card .label {{ font-size: 13px; color: #636e72; margin-top: 4px; }}
</style>
</head>
<body>

<div class="header">
<h1>合同审查报告</h1>
<div class="meta">生成时间: {report.get('generated_at', '')} &nbsp;|&nbsp; 合同类型: {report.get('contract_type', '未知')}</div>
<div class="score-badge">综合评分: {overall_score}/100</div>
<br><span class="verdict">{verdict}</span>
</div>

<div class="section">
<h2>执行摘要</h2>
<p>{executive_summary}</p>
</div>

<div class="section">
<h2>综合统计</h2>
<div class="stat-grid">
<div class="stat-card"><div class="value" style="color:{sev_colors.get(risk_level, '#95a5a6') if False else '#e74c3c' if risk_level in ('high','critical') else '#f39c12' if risk_level == 'medium' else '#27ae60'}">{risk_level_cn}</div><div class="label">风险等级</div></div>
<div class="stat-card"><div class="value">{compliance_analysis.get('score', 0)}</div><div class="label">合规评分</div></div>
<div class="stat-card"><div class="value">{clause_analysis.get('completeness_score', 0)}</div><div class="label">条款完整性</div></div>
</div>
</div>

<div class="section">
<h2>风险分析 (共{risk_analysis.get('total_risks', 0)}项)</h2>
<table>
<tr><th>风险名称</th><th>严重程度</th><th>描述</th><th>建议</th></tr>
{risk_rows if risk_rows else '<tr><td colspan="4">未发现风险</td></tr>'}
</table>
</div>

<div class="section">
<h2>建议 ({len(recommendations)}项)</h2>
{rec_items if rec_items else '<p>暂无建议</p>'}
</div>

<div class="section">
<h2>结论</h2>
<p><strong>判定:</strong> {verdict}</p>
<p><strong>理由:</strong> {conclusion.get('reason', '')}</p>
</div>

</body>
</html>"""
        return html

    def _export_markdown(self, data: Dict) -> str:
        report = data.get("report", data)
        summary = data.get("summary", {})
        overall_score = data.get("overall_score", 0)

        risk_analysis = report.get("risk_analysis", {})
        compliance_analysis = report.get("compliance_analysis", {})
        clause_analysis = report.get("clause_analysis", {})
        recommendations = report.get("recommendations", [])
        conclusion = report.get("conclusion", {})
        executive_summary = report.get("executive_summary", "")

        risk_level = risk_analysis.get("overall_level", "unknown")
        risk_level_cn = {"low": "低", "medium": "中等", "high": "高", "critical": "极高"}.get(risk_level, "未知")

        md_parts = [
            "# 合同审查报告\n",
            f"- **生成时间**: {report.get('generated_at', '')}",
            f"- **合同类型**: {report.get('contract_type', '未知')}",
            f"- **综合评分**: {overall_score}/100\n",
            "## 执行摘要\n",
            executive_summary,
            "## 风险分析\n",
            f"整体风险等级: **{risk_level_cn}** (共{risk_analysis.get('total_risks', 0)}项)\n",
            "| 风险名称 | 严重程度 | 描述 | 建议 |",
            "|----------|----------|------|------|",
        ]

        for r in risk_analysis.get("risks", []):
            md_parts.append(f"| {r.get('name','')} | {r.get('severity','')} | {r.get('description','')} | {r.get('suggestion','')} |")

        md_parts.extend([
            "\n## 建议\n",
        ])
        for i, rec in enumerate(recommendations, 1):
            md_parts.append(f"{i}. **[{rec.get('category','')}]** {rec.get('content','')}")

        md_parts.extend([
            f"\n## 结论\n",
            f"**判定**: {conclusion.get('verdict', '')}",
            f"**理由**: {conclusion.get('reason', '')}",
        ])

        return "\n".join(md_parts)
