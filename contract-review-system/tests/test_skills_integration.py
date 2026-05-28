"""
Day 15: Skills全面集成测试
测试所有12个Skills的功能和集成
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import json
from src.skills import (
    PDFReaderSkill,
    DocxParserSkill,
    OCRProcessorSkill,
    ClauseParserSkill,
    RegulationCheckerSkill,
    CaseRetrieverSkill,
    RiskIdentifierSkill,
    RiskScorerSkill,
    MitigationSuggesterSkill,
    ReportGeneratorSkill,
    VisualizationSkill,
    ExportSkill,
    SkillRegistry,
    all_skills,
    document_skills,
    legal_skills,
    risk_skills,
    report_skills,
)

# 测试合同文本（包含多种风险）
SAMPLE_CONTRACT = """
技术服务合同

甲方：北京创新科技有限公司
乙方：上海智慧软件有限公司

一、合同标的
乙方为甲方提供企业级ERP系统的技术开发服务，包括系统设计、编码实现和测试。

二、服务期限
合同有效期自2024年4月1日至2024年12月31日。

三、服务费用及支付
服务总费用为人民币150万元，甲方应在合同签订后预付全款。

四、验收标准
乙方应按照甲方确认的需求文档进行开发，系统应通过甲方组织的验收测试。

五、知识产权
本合同履行过程中产生的所有技术成果和知识产权归甲方所有。所有衍生的知识产权均归甲方所有。

六、保密条款
双方对本合同内容及履行过程中知悉的对方商业秘密承担保密义务。保密期限为永久保密。所有信息均为保密信息。

七、违约责任
如甲方违约，应承担无限责任，赔偿乙方一切损失。如乙方未能按时交付，应按合同总金额的50%支付违约金。逾期付款的，每日按逾期金额的1%支付违约金。

八、单方解除权
甲方可随时解除本合同，且无需承担任何违约责任。乙方不得解除本合同。

九、争议解决
如发生争议，由乙方所在地法院管辖，同时双方可申请仲裁。

十、不可抗力
因不可抗力导致合同无法履行的，双方均不承担违约责任。

十一、合同终止
本合同到期后自动续约1年，除非任何一方在到期前30日书面通知不续约。
"""


# ============================================================
# 1. 文档处理Skills测试
# ============================================================

def test_pdf_reader_skill():
    """测试PDF读取Skill"""
    print("  [1/12] 测试PDF读取Skill...")
    skill = PDFReaderSkill()

    # 基本信息检查
    assert skill.skill_id == "pdf_reader"
    assert skill.is_enabled

    # 测试不存在的文件
    result = asyncio.run(skill.execute(file_path="nonexistent.pdf"))
    assert "error" in result
    print("    ✓ 文件不存在时返回错误")

    # 测试空参数
    result = asyncio.run(skill.execute())
    assert "error" in result
    print("    ✓ 空参数时返回错误")

    print("    ✓ PDF读取Skill测试通过")
    return True


def test_docx_parser_skill():
    """测试Word文档解析Skill"""
    print("  [2/12] 测试Word文档解析Skill...")
    skill = DocxParserSkill()

    assert skill.skill_id == "docx_parser"
    assert skill.is_enabled

    # 测试不存在的文件
    result = asyncio.run(skill.execute(file_path="nonexistent.docx"))
    assert "error" in result
    print("    ✓ 文件不存在时返回错误")

    # 测试空参数
    result = asyncio.run(skill.execute())
    assert "error" in result
    print("    ✓ 空参数时返回错误")

    print("    ✓ Word文档解析Skill测试通过")
    return True


def test_ocr_processor_skill():
    """测试OCR处理Skill"""
    print("  [3/12] 测试OCR处理Skill...")
    skill = OCRProcessorSkill()

    assert skill.skill_id == "ocr_processor"
    assert skill.is_enabled

    # 测试模拟OCR
    result = asyncio.run(skill.execute(image_bytes=b"test_image"))
    assert "text" in result
    assert result.get("is_mock") is True
    print("    ✓ 模拟OCR处理正常")

    # 测试空参数
    result = asyncio.run(skill.execute())
    assert "error" in result
    print("    ✓ 空参数时返回错误")

    print("    ✓ OCR处理Skill测试通过")
    return True


# ============================================================
# 2. 法律分析Skills测试
# ============================================================

def test_clause_parser_skill():
    """测试条款解析Skill"""
    print("  [4/12] 测试条款解析Skill...")
    skill = ClauseParserSkill()

    assert skill.skill_id == "clause_parser"
    assert skill.is_enabled

    # 测试条款解析
    result = asyncio.run(skill.execute(text=SAMPLE_CONTRACT))

    assert "total_clauses" in result
    assert result["total_clauses"] > 0
    assert "clauses" in result
    assert "type_distribution" in result
    print(f"    ✓ 识别到 {result['total_clauses']} 个条款")

    # 检查条款类型分布
    dist = result["type_distribution"]
    print(f"    ✓ 条款类型分布: {dist}")

    # 检查摘要
    summary = result.get("summary", {})
    assert "has_liability_clauses" in summary
    assert "has_dispute_resolution" in summary
    print(f"    ✓ 违约条款: {summary['has_liability_clauses']}")
    print(f"    ✓ 争议解决: {summary['has_dispute_resolution']}")

    # 测试空文本
    result = asyncio.run(skill.execute(text=""))
    assert "error" in result
    print("    ✓ 空文本时返回错误")

    print("    ✓ 条款解析Skill测试通过")
    return True


def test_regulation_checker_skill():
    """测试法规检查Skill"""
    print("  [5/12] 测试法规检查Skill...")
    skill = RegulationCheckerSkill()

    assert skill.skill_id == "regulation_checker"
    assert skill.is_enabled

    # 测试法规检查
    result = asyncio.run(skill.execute(text=SAMPLE_CONTRACT, contract_type="service"))

    assert "total_rules_checked" in result
    assert "violations_found" in result
    assert "violations" in result
    assert "compliance_score" in result
    print(f"    ✓ 检查了 {result['total_rules_checked']} 条规则")
    print(f"    ✓ 发现 {result['violations_found']} 个违规")
    print(f"    ✓ 合规分数: {result['compliance_score']}")

    # 检查违规详情
    for v in result.get("violations", [])[:3]:
        print(f"    ⚠ {v['regulation']}: {v['description'][:50]}...")

    # 测试空文本
    result = asyncio.run(skill.execute(text=""))
    assert "error" in result
    print("    ✓ 空文本时返回错误")

    print("    ✓ 法规检查Skill测试通过")
    return True


def test_case_retriever_skill():
    """测试案例检索Skill"""
    print("  [6/12] 测试案例检索Skill...")
    skill = CaseRetrieverSkill()

    assert skill.skill_id == "case_retriever"
    assert skill.is_enabled

    # 测试关键词搜索
    result = asyncio.run(skill.execute(keywords=["违约金", "过高"]))
    assert "total_found" in result
    assert result["total_found"] > 0
    print(f"    ✓ 搜索'违约金,过高'找到 {result['total_found']} 个案例")

    # 测试类别搜索
    result = asyncio.run(skill.execute(category="劳动争议"))
    assert "total_found" in result
    print(f"    ✓ 类别'劳动争议'找到 {result['total_found']} 个案例")

    # 测试风险等级搜索
    result = asyncio.run(skill.execute(risk_level="high"))
    assert "total_found" in result
    print(f"    ✓ 高风险案例: {result['total_found']} 个")

    # 测试空搜索（返回所有）
    result = asyncio.run(skill.execute())
    assert "total_found" in result
    print(f"    ✓ 全部案例: {result['total_found']} 个")

    # 测试按ID获取
    case = skill.get_case_by_id("case_001")
    assert case is not None
    print(f"    ✓ 按ID获取案例: {case['title']}")

    print("    ✓ 案例检索Skill测试通过")
    return True


# ============================================================
# 3. 风险管理Skills测试
# ============================================================

def test_risk_identifier_skill():
    """测试风险识别Skill"""
    print("  [7/12] 测试风险识别Skill...")
    skill = RiskIdentifierSkill()

    assert skill.skill_id == "risk_identifier"
    assert skill.is_enabled

    # 测试风险识别
    result = asyncio.run(skill.execute(text=SAMPLE_CONTRACT))

    assert "total_risks" in result
    assert "risks" in result
    assert "severity_distribution" in result
    print(f"    ✓ 识别到 {result['total_risks']} 个风险")

    # 检查风险分布
    sev_dist = result["severity_distribution"]
    print(f"    ✓ 严重程度分布: 高={sev_dist.get('high', 0)}, 中={sev_dist.get('medium', 0)}, 低={sev_dist.get('low', 0)}")

    # 检查风险详情
    for risk in result.get("risks", [])[:5]:
        print(f"    ⚠ [{risk['severity']}] {risk['name']}: {risk['description'][:40]}...")

    # 测试按类别过滤
    result = asyncio.run(skill.execute(text=SAMPLE_CONTRACT, categories=["liability"]))
    print(f"    ✓ 责任类风险: {result.get('total_risks', 0)} 个")

    # 测试空文本
    result = asyncio.run(skill.execute(text=""))
    assert "error" in result
    print("    ✓ 空文本时返回错误")

    print("    ✓ 风险识别Skill测试通过")
    return True


def test_risk_scorer_skill():
    """测试风险量化Skill"""
    print("  [8/12] 测试风险量化Skill...")
    skill = RiskScorerSkill()

    assert skill.skill_id == "risk_scorer"
    assert skill.is_enabled

    # 模拟风险数据
    sample_risks = [
        {"name": "无限责任风险", "severity": "high", "category": "liability"},
        {"name": "预付款风险", "severity": "medium", "category": "payment"},
        {"name": "保密期限过长", "severity": "medium", "category": "confidentiality"},
        {"name": "单方解除权不对等", "severity": "high", "category": "termination"},
        {"name": "争议解决机制缺失", "severity": "high", "category": "dispute"},
    ]

    result = asyncio.run(skill.execute(risks=sample_risks))

    assert "overall_score" in result
    assert "risk_level" in result
    assert "scored_risks" in result
    assert "risk_matrix" in result
    print(f"    ✓ 整体风险分数: {result['overall_score']}")
    print(f"    ✓ 风险等级: {result['risk_level']}")
    print(f"    ✓ 量化风险数: {len(result['scored_risks'])}")

    # 检查风险矩阵
    matrix = result["risk_matrix"]
    for level in ["critical", "high", "medium", "low"]:
        count = len(matrix.get(level, []))
        if count > 0:
            print(f"    ✓ 风险矩阵 [{level}]: {count} 项")

    # 检查类别统计
    cat_stats = result.get("category_stats", {})
    for cat, stats in cat_stats.items():
        print(f"    ✓ 类别 '{cat}': {stats['count']} 项, 平均分 {stats['avg_score']}")

    # 测试空风险列表
    result = asyncio.run(skill.execute(risks=[]))
    assert "error" in result
    print("    ✓ 空风险列表时返回错误")

    print("    ✓ 风险量化Skill测试通过")
    return True


def test_mitigation_suggester_skill():
    """测试风险缓解Skill"""
    print("  [9/12] 测试风险缓解Skill...")
    skill = MitigationSuggesterSkill()

    assert skill.skill_id == "mitigation_suggester"
    assert skill.is_enabled

    # 模拟风险数据
    sample_risks = [
        {"risk_id": "unlimited_liability", "name": "无限责任风险", "severity": "high", "category": "liability", "score": 45},
        {"risk_id": "payment_advance", "name": "预付款风险", "severity": "medium", "category": "payment", "score": 26},
        {"risk_id": "confidentiality_permanent", "name": "保密期限过长", "severity": "medium", "category": "confidentiality", "score": 22},
        {"risk_id": "termination_unilateral", "name": "单方解除权不对等", "severity": "high", "category": "termination", "score": 36},
        {"risk_id": "dispute_no_mechanism", "name": "争议解决机制缺失", "severity": "high", "category": "dispute", "score": 39},
    ]

    result = asyncio.run(skill.execute(risks=sample_risks))

    assert "total_mitigations" in result
    assert "mitigations" in result
    assert "priority_distribution" in result
    print(f"    ✓ 生成 {result['total_mitigations']} 条缓解建议")

    # 检查优先级分布
    pri_dist = result["priority_distribution"]
    print(f"    ✓ 优先级分布: 高={pri_dist.get('high', 0)}, 中={pri_dist.get('medium', 0)}, 低={pri_dist.get('low', 0)}")

    # 检查缓解建议详情
    for m in result.get("mitigations", [])[:3]:
        print(f"    💡 [{m['priority']}] {m['risk_name']}: {m['mitigation'][:40]}...")
        if m.get("clause_template"):
            print(f"       📝 条款模板: {m['clause_template'][:50]}...")

    # 测试获取模板
    template = skill.get_mitigation_by_risk_id("unlimited_liability")
    assert "mitigation" in template
    assert "clause_template" in template
    print(f"    ✓ 获取模板: {template['mitigation'][:40]}...")

    # 测试空风险列表
    result = asyncio.run(skill.execute(risks=[]))
    assert "error" in result
    print("    ✓ 空风险列表时返回错误")

    print("    ✓ 风险缓解Skill测试通过")
    return True


# ============================================================
# 4. 报告生成Skills测试
# ============================================================

def test_report_generator_skill():
    """测试综合报告生成Skill"""
    print("  [10/12] 测试综合报告生成Skill...")
    skill = ReportGeneratorSkill()

    assert skill.skill_id == "report_generator"
    assert skill.is_enabled

    # 模拟各阶段结果
    document_info = {
        "contract_type": "service",
        "parties": ["北京创新科技有限公司", "上海智慧软件有限公司"],
        "text_length": 1500,
        "sections_count": 11,
    }

    clause_analysis = {
        "analysis": {
            "completeness": {
                "completeness_score": 0.7,
                "missing_clauses": ["保密条款", "不可抗力条款"],
            },
            "rights_obligations": {
                "rights_count": 5,
                "obligations_count": 12,
                "balance_ratio": 0.42,
                "balance_assessment": "义务偏重",
            },
        },
        "issues": [
            {"type": "条款缺失", "severity": "medium", "message": "缺少保密条款", "suggestion": "建议增加保密条款"},
        ],
    }

    risk_assessment = {
        "risk_level": "high",
        "total_risks": 5,
        "risks": [
            {"name": "无限责任风险", "severity": "high", "suggestion": "建议设置责任上限"},
            {"name": "预付款风险", "severity": "medium", "suggestion": "建议分期付款"},
        ],
        "recommendations": [],
    }

    compliance_check = {
        "compliance_status": "partial",
        "score": 65,
        "compliance_violations": [
            {"clause": "免责条款", "regulation": "《民法典》第506条", "severity": "high", "suggestion": "建议修改免责条款"},
        ],
        "missing_clauses": ["争议解决条款"],
    }

    result = asyncio.run(skill.execute(
        document_info=document_info,
        clause_analysis=clause_analysis,
        risk_assessment=risk_assessment,
        compliance_check=compliance_check,
        contract_type="service",
    ))

    assert "report" in result
    assert "overall_score" in result
    assert "summary" in result
    print(f"    ✓ 综合评分: {result['overall_score']}/100")
    print(f"    ✓ 风险等级: {result['summary']['risk_level']}")
    print(f"    ✓ 合规分数: {result['summary']['compliance_score']}")
    print(f"    ✓ 完整性分数: {result['summary']['completeness_score']}")
    print(f"    ✓ 结论: {result['summary']['verdict']}")

    # 检查报告结构
    report = result["report"]
    assert "executive_summary" in report
    assert "risk_analysis" in report
    assert "compliance_analysis" in report
    assert "recommendations" in report
    assert "conclusion" in report
    print(f"    ✓ 执行摘要: {report['executive_summary'][:60]}...")
    print(f"    ✓ 建议数量: {len(report['recommendations'])}")

    print("    ✓ 综合报告生成Skill测试通过")
    return True


def test_visualization_skill():
    """测试报告可视化Skill"""
    print("  [11/12] 测试报告可视化Skill...")
    skill = VisualizationSkill()

    assert skill.skill_id == "visualization"
    assert skill.is_enabled

    # 模拟报告数据
    report_data = {
        "risk_analysis": {
            "overall_level": "high",
            "total_risks": 5,
            "distribution": {"high": 2, "medium": 2, "low": 1},
            "risks": [
                {"name": "无限责任风险", "severity": "high", "category": "liability"},
                {"name": "预付款风险", "severity": "medium", "category": "payment"},
                {"name": "保密期限过长", "severity": "medium", "category": "confidentiality"},
                {"name": "单方解除权不对等", "severity": "high", "category": "termination"},
                {"name": "争议解决机制缺失", "severity": "low", "category": "dispute"},
            ],
        },
        "compliance_analysis": {
            "score": 65,
            "status": "partial",
            "violations": [{"regulation": "《民法典》第506条"}],
            "missing_clauses": ["争议解决条款"],
            "violations_count": 1,
        },
        "clause_analysis": {
            "completeness_score": 0.7,
            "missing_clauses": ["保密条款"],
            "issues_count": 3,
        },
        "overall_score": 65,
    }

    # 测试所有图表
    result = asyncio.run(skill.execute(report_data=report_data, chart_types=["all"]))

    assert "charts" in result
    assert result["chart_count"] > 0
    print(f"    ✓ 生成 {result['chart_count']} 个图表")

    charts = result["charts"]
    expected_charts = ["risk_pie", "risk_bar", "compliance_radar", "completeness_progress", "score_gauge", "issue_heatmap"]
    for chart_name in expected_charts:
        assert chart_name in charts, f"缺少图表: {chart_name}"
        chart = charts[chart_name]
        assert "type" in chart
        assert "title" in chart
        print(f"    ✓ {chart_name}: {chart['type']} - {chart['title']}")

    # 测试单个图表
    result = asyncio.run(skill.execute(report_data=report_data, chart_types=["risk_pie"]))
    assert "risk_pie" in result["charts"]
    print("    ✓ 单图表生成正常")

    print("    ✓ 报告可视化Skill测试通过")
    return True


def test_export_skill():
    """测试报告导出Skill"""
    print("  [12/12] 测试报告导出Skill...")
    skill = ExportSkill()

    assert skill.skill_id == "export"
    assert skill.is_enabled

    # 模拟报告数据
    report_data = {
        "report": {
            "title": "合同审查报告",
            "generated_at": "2024-03-15T10:00:00",
            "contract_type": "service",
            "executive_summary": "本报告针对一份技术服务合同进行审查。",
            "risk_analysis": {
                "overall_level": "high",
                "total_risks": 3,
                "risks": [
                    {"name": "无限责任风险", "severity": "high", "description": "合同约定了无限责任", "suggestion": "建议设置责任上限"},
                ],
            },
            "compliance_analysis": {
                "score": 65,
                "status": "partial",
                "violations": [],
                "missing_clauses": [],
            },
            "clause_analysis": {
                "completeness_score": 0.7,
                "missing_clauses": [],
                "issues_count": 2,
                "issues": [],
            },
            "recommendations": [
                {"priority": "high", "category": "风险", "content": "建议修改违约责任条款"},
            ],
            "conclusion": {
                "verdict": "建议修改后签署",
                "reason": "合同存在高风险条款",
            },
        },
        "overall_score": 65,
        "summary": {"risk_level": "high"},
    }

    # 测试HTML导出
    result = asyncio.run(skill.execute(report_data=report_data, format="html"))
    assert result["format"] == "html"
    assert len(result["content"]) > 0
    assert "<!DOCTYPE html>" in result["content"]
    print(f"    ✓ HTML导出: {result['size']} 字节")

    # 测试Markdown导出
    result = asyncio.run(skill.execute(report_data=report_data, format="markdown"))
    assert result["format"] == "markdown"
    assert len(result["content"]) > 0
    assert "# 合同审查报告" in result["content"]
    print(f"    ✓ Markdown导出: {result['size']} 字节")

    # 测试JSON导出
    result = asyncio.run(skill.execute(report_data=report_data, format="json"))
    assert result["format"] == "json"
    parsed = json.loads(result["content"])
    assert "report" in parsed
    print(f"    ✓ JSON导出: {result['size']} 字节")

    # 测试不支持的格式
    result = asyncio.run(skill.execute(report_data=report_data, format="xml"))
    assert "error" in result
    print("    ✓ 不支持的格式返回错误")

    print("    ✓ 报告导出Skill测试通过")
    return True


# ============================================================
# 5. SkillRegistry集成测试
# ============================================================

def test_skill_registry_integration():
    """测试SkillRegistry完整集成"""
    print("  [附加] 测试SkillRegistry完整集成...")

    registry = SkillRegistry()

    # 注册所有Skills
    for skill in all_skills:
        registry.register_skill(skill)

    # 检查注册结果
    skills = registry.list_skills()
    assert len(skills) == 12
    print(f"    ✓ 注册了 {len(skills)} 个Skills")

    tools = registry.list_tools()
    assert len(tools) == 12
    print(f"    ✓ 工具名称: {tools}")

    # 测试通过skill_id获取
    skill = registry.get_skill("risk_identifier")
    assert skill is not None
    assert skill.name == "风险识别"
    print("    ✓ 通过skill_id获取: 风险识别")

    # 测试通过tool_name获取
    skill = registry.get_skill_by_tool_name("clause_parser")
    assert skill is not None
    assert skill.name == "条款解析"
    print("    ✓ 通过tool_name获取: 条款解析")

    # 测试执行Skill
    result = asyncio.run(registry.execute_skill(
        "clause_parser",
        text=SAMPLE_CONTRACT
    ))
    assert "total_clauses" in result
    print(f"    ✓ 执行条款解析: {result['total_clauses']} 个条款")

    # 测试禁用/启用
    skill = registry.get_skill("ocr_processor")
    skill.disable()
    assert not skill.is_enabled
    result = asyncio.run(registry.execute_skill("ocr_processor", image_bytes=b"test"))
    assert "error" in result
    print("    ✓ 禁用Skill后无法执行")

    skill.enable()
    assert skill.is_enabled
    result = asyncio.run(registry.execute_skill("ocr_processor", image_bytes=b"test"))
    assert "text" in result
    print("    ✓ 启用Skill后可执行")

    # 测试取消注册
    registry.unregister_skill("ocr_processor")
    assert registry.get_skill("ocr_processor") is None
    print("    ✓ 取消注册Skill")

    print("    ✓ SkillRegistry完整集成测试通过")
    return True


def run_all_tests():
    """运行所有Skills集成测试"""
    print("=" * 60)
    print("Day 15: Skills全面集成测试")
    print("=" * 60)

    tests = [
        ("PDF读取Skill", test_pdf_reader_skill),
        ("Word文档解析Skill", test_docx_parser_skill),
        ("OCR处理Skill", test_ocr_processor_skill),
        ("条款解析Skill", test_clause_parser_skill),
        ("法规检查Skill", test_regulation_checker_skill),
        ("案例检索Skill", test_case_retriever_skill),
        ("风险识别Skill", test_risk_identifier_skill),
        ("风险量化Skill", test_risk_scorer_skill),
        ("风险缓解Skill", test_mitigation_suggester_skill),
        ("综合报告生成Skill", test_report_generator_skill),
        ("报告可视化Skill", test_visualization_skill),
        ("报告导出Skill", test_export_skill),
        ("SkillRegistry集成", test_skill_registry_integration),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"  ✗ {name} 测试失败: {e}")
            results.append((name, False))

    passed = sum(1 for _, r in results if r)
    total = len(results)

    print("=" * 60)
    print(f"测试结果: {passed}/{total} 通过")
    print("=" * 60)

    for name, result in results:
        status = "✓" if result else "✗"
        print(f"  {status} {name}")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
