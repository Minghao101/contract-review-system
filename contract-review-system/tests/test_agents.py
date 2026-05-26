"""
Agent测试模块
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from src.agents import (
    CoordinatorAgent,
    DocumentParserAgent,
    ClauseAnalysisAgent,
    RiskAssessmentAgent,
    ReportGeneratorAgent,
)


# 测试合同文本
SAMPLE_CONTRACT = """
技术服务合同

甲方：北京科技有限公司
乙方：上海软件有限公司

一、合同标的
乙方为甲方提供技术开发服务，包括系统设计、编码实现和测试。

二、服务期限
合同有效期自2024年1月1日至2024年12月31日。

三、服务费用
服务总费用为人民币50万元，甲方应在合同签订后预付全款。

四、违约责任
如甲方违约，应承担无限责任，赔偿乙方一切损失。

五、争议解决
如发生争议，由乙方所在地法院管辖。
"""


def test_document_parser():
    """测试文档解析Agent"""
    print("测试文档解析Agent...")

    agent = DocumentParserAgent()

    task = {
        "contract_text": SAMPLE_CONTRACT,
        "contract_type": "service"
    }

    result = asyncio.run(agent.process(task))

    assert "document_info" in result
    assert result["document_info"]["contract_type"] == "service"
    assert len(result["sections"]) > 0
    assert len(result["dates"]) > 0

    print(f"  - 合同类型: {result['document_info']['contract_type']}")
    print(f"  - 条款数: {len(result['sections'])}")
    print(f"  - 日期数: {len(result['dates'])}")
    print("文档解析Agent测试通过！")
    return True


def test_clause_analysis():
    """测试条款分析Agent"""
    print("测试条款分析Agent...")

    agent = ClauseAnalysisAgent()

    task = {
        "contract_text": SAMPLE_CONTRACT,
        "review_focus": ["违约责任", "付款条款"]
    }

    result = asyncio.run(agent.process(task))

    assert "analysis" in result
    assert "completeness" in result["analysis"]
    assert "ambiguous_clauses" in result["analysis"]

    completeness = result["analysis"]["completeness"]
    print(f"  - 完整性得分: {completeness.get('completeness_score', 0):.2%}")
    print(f"  - 缺少条款: {completeness.get('missing_clauses', completeness.get('missing', []))}")
    print(f"  - 模糊条款数: {len(result['analysis']['ambiguous_clauses'])}")
    print("条款分析Agent测试通过！")
    return True


def test_risk_assessment():
    """测试风险评估Agent"""
    print("测试风险评估Agent...")

    agent = RiskAssessmentAgent()

    task = {
        "contract_text": SAMPLE_CONTRACT,
        "contract_type": "service"
    }

    result = asyncio.run(agent.process(task))

    assert "risk_level" in result
    assert "risks" in result
    assert "recommendations" in result

    print(f"  - 风险等级: {result['risk_level']}")
    print(f"  - 风险数量: {len(result['risks'])}")
    for risk in result['risks'][:3]:
        print(f"    - {risk['name']} ({risk['severity']})")
    print("风险评估Agent测试通过！")
    return True


def test_report_generator():
    """测试报告生成Agent"""
    print("测试报告生成Agent...")

    agent = ReportGeneratorAgent()

    # 模拟前面阶段的结果
    previous_results = {
        "parse_document": {
            "result": {
                "document_info": {
                    "contract_type": "service",
                    "text_length": len(SAMPLE_CONTRACT),
                    "sections_count": 5,
                }
            }
        },
        "analyze_clauses": {
            "result": {
                "analysis": {
                    "completeness": {
                        "score": 0.8,
                        "found": ["服务内容", "服务期限", "服务费用", "违约责任"],
                        "missing": ["保密条款"],
                    }
                }
            }
        },
        "assess_risks": {
            "result": {
                "risk_level": "high",
                "risks": [
                    {"name": "无限责任风险", "severity": "high"},
                    {"name": "预付全款风险", "severity": "medium"},
                ],
                "recommendations": [
                    {"suggestion": "修改违约责任条款"}
                ]
            }
        }
    }

    task = {"previous_results": previous_results}

    result = asyncio.run(agent.process(task))

    assert "report" in result
    assert "summary" in result
    assert "generated_at" in result

    report = result["report"]
    print(f"  - 报告标题: {report['title']}")
    print(f"  - 结论: {report['conclusion']['verdict']}")
    print("报告生成Agent测试通过！")
    return True


def test_coordinator():
    """测试协调器Agent"""
    print("测试协调器Agent...")

    # 创建协调器
    coordinator = CoordinatorAgent()

    # 创建并注册其他Agent
    doc_parser = DocumentParserAgent()
    clause_analyst = ClauseAnalysisAgent()
    risk_assessor = RiskAssessmentAgent()
    report_generator = ReportGeneratorAgent()

    coordinator.register_agent(doc_parser)
    coordinator.register_agent(clause_analyst)
    coordinator.register_agent(risk_assessor)
    coordinator.register_agent(report_generator)

    # 检查注册状态
    agents = coordinator.get_registered_agents()
    assert len(agents) == 4

    # 执行审查任务
    task = {
        "contract_text": SAMPLE_CONTRACT,
        "contract_type": "service",
        "review_focus": ["违约责任"]
    }

    result = asyncio.run(coordinator.process(task))

    assert "status" in result
    assert result["status"] in ["completed", "partial_failed"]
    assert "risk_level" in result

    print(f"  - 审查状态: {result['status']}")
    print(f"  - 风险等级: {result['risk_level']}")
    print(f"  - 已注册Agent数: {len(agents)}")
    print("协调器Agent测试通过！")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("开始运行Agent测试")
    print("=" * 50)

    tests = [
        test_document_parser(),
        test_clause_analysis(),
        test_risk_assessment(),
        test_report_generator(),
        test_coordinator(),
    ]

    passed = sum(1 for t in tests if t)

    print("=" * 50)
    print(f"测试完成: {passed}/{len(tests)} 通过")
    print("=" * 50)

    return passed == len(tests)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
