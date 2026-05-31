"""
Day 24: 结果展示与交互优化 - 测试文件

测试内容：
- 结果展示模板（result_display.py）的数据处理逻辑
- 进度追踪器（progress_tracker.py）的状态管理
- 格式化函数和辅助工具
- 端到端流程验证

注意：Streamlit UI渲染函数需要Streamlit运行时环境，
本测试聚焦于非UI的数据逻辑层。
"""
import sys
import time
import json
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 测试计数器
passed = 0
failed = 0
total = 0


def run_test(test_name, test_func):
    """运行单个测试"""
    global passed, failed, total
    total += 1
    try:
        test_func()
        passed += 1
        print(f"  ✅ {test_name}")
    except Exception as e:
        failed += 1
        print(f"  ❌ {test_name}: {e}")


# ============================================================
# 1. 模块导入测试
# ============================================================

def test_progress_tracker_import():
    """测试进度追踪器模块导入"""
    from frontend.components.progress_tracker import (
        ReviewProgressTracker,
        REVIEW_STEPS,
        render_progress_tracker,
        render_compact_progress,
        render_loading_spinner,
        render_agent_status_card,
        render_status_message,
        create_review_tracker,
        format_duration,
        get_status_emoji,
    )
    assert ReviewProgressTracker is not None
    assert REVIEW_STEPS is not None
    assert callable(render_progress_tracker)
    assert callable(create_review_tracker)
    assert callable(format_duration)
    assert callable(get_status_emoji)


def test_result_display_import():
    """测试结果展示模块导入"""
    from frontend.components.result_display import (
        render_result_card,
        render_metric_card,
        render_parse_result,
        render_clause_result,
        render_risk_result,
        render_compliance_result,
        render_report_result,
        render_review_timeline,
        render_full_review_result,
        render_quick_risk_result,
        render_quick_summary,
        render_review_result,
        _truncate,
        _generate_text_summary,
    )
    assert callable(render_result_card)
    assert callable(_truncate)
    assert callable(_generate_text_summary)


def test_review_steps_definition():
    """测试审查步骤定义"""
    from frontend.components.progress_tracker import REVIEW_STEPS

    assert len(REVIEW_STEPS) == 7
    step_ids = [s["id"] for s in REVIEW_STEPS]
    assert "init" in step_ids
    assert "parse" in step_ids
    assert "clause" in step_ids
    assert "risk" in step_ids
    assert "compliance" in step_ids
    assert "report" in step_ids
    assert "complete" in step_ids

    # 每个步骤必须有 id, name, icon, description
    for step in REVIEW_STEPS:
        assert "id" in step
        assert "name" in step
        assert "icon" in step
        assert "description" in step


# ============================================================
# 2. ReviewProgressTracker 核心逻辑测试
# ============================================================

def test_tracker_creation():
    """测试追踪器创建"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    assert tracker is not None
    assert len(tracker.steps) == 7
    assert len(tracker.step_states) == 7
    assert tracker.end_time is None


def test_tracker_custom_steps():
    """测试自定义步骤"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    custom_steps = [
        {"id": "step1", "name": "步骤1", "icon": "1️⃣", "description": "测试步骤1"},
        {"id": "step2", "name": "步骤2", "icon": "2️⃣", "description": "测试步骤2"},
    ]
    tracker = ReviewProgressTracker(steps=custom_steps)
    assert len(tracker.steps) == 2
    assert len(tracker.step_states) == 2


def test_tracker_start_step():
    """测试开始步骤"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    tracker.start_step("init", "正在初始化")
    state = tracker.step_states["init"]
    assert state["status"] == "running"
    assert state["start_time"] is not None
    assert state["message"] == "正在初始化"


def test_tracker_complete_step():
    """测试完成步骤"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    tracker.start_step("parse")
    time.sleep(0.01)
    tracker.complete_step("parse", "解析完成")
    state = tracker.step_states["parse"]
    assert state["status"] == "completed"
    assert state["end_time"] is not None
    assert state["progress"] == 100
    assert state["duration"] is not None
    assert state["duration"] >= 0


def test_tracker_fail_step():
    """测试失败步骤"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    tracker.start_step("risk")
    time.sleep(0.01)
    tracker.fail_step("risk", "超时失败")
    state = tracker.step_states["risk"]
    assert state["status"] == "failed"
    assert state["end_time"] is not None
    assert state["message"] == "超时失败"


def test_tracker_update_progress():
    """测试更新进度"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    tracker.start_step("clause")
    tracker.update_progress("clause", 50, "分析中")
    state = tracker.step_states["clause"]
    assert state["progress"] == 50
    assert state["message"] == "分析中"

    # 测试边界值
    tracker.update_progress("clause", 150)
    assert tracker.step_states["clause"]["progress"] == 100

    tracker.update_progress("clause", -10)
    assert tracker.step_states["clause"]["progress"] == 0


def test_tracker_overall_progress():
    """测试总体进度计算"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()

    # 初始进度为0
    assert tracker.get_overall_progress() == 0

    # 完成一半步骤
    tracker.complete_step("init")
    tracker.complete_step("parse")
    tracker.complete_step("clause")
    # 7个步骤，3个完成 = 3/7 * 100 ≈ 42
    overall = tracker.get_overall_progress()
    assert overall > 0
    assert overall <= 100

    # 全部完成
    for step in tracker.steps:
        tracker.complete_step(step["id"])
    assert tracker.get_overall_progress() == 100


def test_tracker_duration():
    """测试耗时统计"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    time.sleep(0.05)
    duration = tracker.get_total_duration()
    assert duration >= 0.04  # 允许微小误差

    # 单步骤耗时
    tracker.start_step("init")
    time.sleep(0.02)
    tracker.complete_step("init")
    step_duration = tracker.get_step_duration("init")
    assert step_duration is not None
    assert step_duration >= 0.01


def test_tracker_finish():
    """测试完成整个审查"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    tracker.start_step("init")
    tracker.complete_step("init")
    tracker.start_step("parse")

    tracker.finish()

    assert tracker.end_time is not None
    # parse 步骤应该被自动完成
    assert tracker.step_states["parse"]["status"] == "completed"
    # 未开始的步骤也应被完成
    assert tracker.step_states["clause"]["status"] == "completed"


def test_tracker_status_summary():
    """测试状态摘要"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    tracker.complete_step("init")
    tracker.complete_step("parse")
    tracker.fail_step("risk")

    summary = tracker.get_status_summary()
    assert summary["total_steps"] == 7
    assert summary["completed"] == 2
    assert summary["failed"] == 1
    assert summary["running"] == 0
    assert summary["total_duration"] >= 0
    assert summary["overall_progress"] >= 0


def test_tracker_serialization():
    """测试序列化"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    tracker.start_step("init")
    tracker.complete_step("init")

    data = tracker.to_dict()
    assert "steps" in data
    assert "overall_progress" in data
    assert "total_duration" in data
    assert "status_summary" in data
    assert len(data["steps"]) == 7

    # 验证步骤数据包含原始定义和状态
    init_step = data["steps"][0]
    assert init_step["id"] == "init"
    assert init_step["status"] == "completed"


def test_tracker_auto_complete_previous():
    """测试自动完成之前的步骤"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    # 直接开始第三个步骤，前面的应该保持pending
    tracker.start_step("risk")

    # init 和 parse 仍为 pending
    assert tracker.step_states["init"]["status"] == "pending"
    assert tracker.step_states["parse"]["status"] == "pending"
    # risk 为 running
    assert tracker.step_states["risk"]["status"] == "running"


def test_create_review_tracker():
    """测试便捷创建函数"""
    from frontend.components.progress_tracker import create_review_tracker, ReviewProgressTracker

    tracker = create_review_tracker()
    assert isinstance(tracker, ReviewProgressTracker)
    assert len(tracker.steps) == 7


# ============================================================
# 3. 格式化函数测试
# ============================================================

def test_format_duration_milliseconds():
    """测试毫秒级格式化"""
    from frontend.components.progress_tracker import format_duration

    assert format_duration(0.5) == "500ms"
    assert format_duration(0.001) == "1ms"


def test_format_duration_seconds():
    """测试秒级格式化"""
    from frontend.components.progress_tracker import format_duration

    result = format_duration(5.3)
    assert "5.3s" in result


def test_format_duration_minutes():
    """测试分钟级格式化"""
    from frontend.components.progress_tracker import format_duration

    result = format_duration(125)
    assert "2m" in result


def test_get_status_emoji():
    """测试状态emoji"""
    from frontend.components.progress_tracker import get_status_emoji

    assert get_status_emoji("completed") == "✅"
    assert get_status_emoji("running") == "🔄"
    assert get_status_emoji("failed") == "❌"
    assert get_status_emoji("pending") == "⏳"
    assert get_status_emoji("success") == "✅"
    assert get_status_emoji("warning") == "⚠️"
    assert get_status_emoji("error") == "❌"
    assert get_status_emoji("info") == "ℹ️"
    assert get_status_emoji("unknown") == "❓"


def test_truncate_short_text():
    """测试短文本截断"""
    from frontend.components.result_display import _truncate

    assert _truncate("hello") == "hello"
    assert _truncate("") == "未知"
    assert _truncate(None) == "未知"


def test_truncate_long_text():
    """测试长文本截断"""
    from frontend.components.result_display import _truncate

    result = _truncate("这是一段很长的文本内容", 5)
    assert len(result) == 8  # 5 chars + "..."
    assert result.endswith("...")


# ============================================================
# 4. 文本摘要生成测试
# ============================================================

def test_generate_text_summary():
    """测试文本摘要生成"""
    from frontend.components.result_display import _generate_text_summary

    result = {
        "status": "completed",
        "parse_result": {
            "document_info": {
                "type": "技术服务合同",
                "party_a": "甲方公司",
                "party_b": "乙方公司",
            }
        },
        "risk_result": {
            "risks": [
                {"level": "high", "title": "违约金过高", "description": "违约金条款不合理"},
                {"level": "low", "title": "格式问题", "description": "部分条款格式不规范"},
            ]
        },
        "compliance_result": {
            "issues": [
                {"description": "缺少知识产权条款"},
            ]
        },
    }

    summary = _generate_text_summary(result)
    assert "合同审查报告摘要" in summary
    assert "completed" in summary
    assert "技术服务合同" in summary
    assert "甲方公司" in summary
    assert "HIGH" in summary
    assert "违约金过高" in summary
    assert "知识产权条款" in summary


def test_generate_text_summary_minimal():
    """测试最小数据的文本摘要"""
    from frontend.components.result_display import _generate_text_summary

    result = {"status": "failed"}
    summary = _generate_text_summary(result)
    assert "failed" in summary
    assert "合同审查报告摘要" in summary


def test_generate_text_summary_full_result():
    """测试完整审查结果的文本摘要"""
    from frontend.components.result_display import _generate_text_summary

    result = {
        "status": "completed",
        "parse_result": {
            "document_info": {"type": "劳动合同", "party_a": "A", "party_b": "B"}
        },
        "risk_result": {"risks": []},
        "compliance_result": {"issues": []},
    }
    summary = _generate_text_summary(result)
    assert "劳动合同" in summary
    assert "A" in summary


# ============================================================
# 5. 快速摘要测试
# ============================================================

def test_render_quick_summary():
    """测试快速摘要渲染"""
    from frontend.components.result_display import render_quick_summary

    result = {
        "status": "completed",
        "risk_result": {
            "risks": [
                {"level": "high", "title": "高风险项"},
                {"level": "medium", "title": "中风险项"},
            ]
        },
        "compliance_result": {
            "issues": [{"description": "合规问题1"}]
        },
    }

    summary = render_quick_summary(result)
    assert "completed" in summary
    assert "2" in summary  # 2 risks
    assert "1" in summary  # 1 compliance issue
    assert "高风险" in summary


def test_render_quick_summary_no_risks():
    """测试无风险的快速摘要"""
    from frontend.components.result_display import render_quick_summary

    result = {"status": "completed"}
    summary = render_quick_summary(result)
    assert "completed" in summary


# ============================================================
# 6. 审查结果数据结构测试
# ============================================================

def test_full_result_structure():
    """测试完整审查结果数据结构"""
    result = {
        "status": "completed",
        "steps": [
            {"name": "文档解析", "status": "completed", "duration": "1.2s", "agent": "DocumentParser"},
            {"name": "条款分析", "status": "completed", "duration": "0.8s", "agent": "ClauseAnalysis"},
            {"name": "风险评估", "status": "running", "agent": "RiskAssessment"},
        ],
        "parse_result": {
            "document_info": {
                "type": "技术服务合同",
                "party_a": "北京创新科技有限公司",
                "party_b": "上海智慧软件有限公司",
                "amount": {"value": "150万元"},
                "date_range": {"start": "2024-04-01", "end": "2024-12-31"},
            },
            "key_clauses": [
                {"title": "合同标的", "summary": "ERP系统开发"},
                {"title": "保密条款", "summary": "双方保密义务"},
            ],
            "metadata": {"text_length": 500, "paragraph_count": 10, "extraction_time": 0.5},
        },
        "clause_result": {
            "clauses": [
                {"title": "第一条", "summary": "合同标的", "importance": "high", "risk_level": "low",
                 "key_points": ["开发ERP系统"], "obligations": ["乙方交付"]},
                {"title": "第六条", "summary": "违约责任", "importance": "high", "risk_level": "high",
                 "key_points": ["无限责任"]},
            ]
        },
        "risk_result": {
            "risks": [
                {"level": "high", "title": "无限违约金", "description": "甲方承担无限责任",
                 "suggestion": "修改为有限责任", "clause": "第六条"},
                {"level": "medium", "title": "管辖权", "description": "争议由乙方所在地法院管辖",
                 "suggestion": "改为中立仲裁"},
                {"level": "low", "title": "格式问题", "description": "部分条款格式不规范"},
            ]
        },
        "compliance_result": {
            "compliance_score": 72,
            "issues": [
                {"severity": "high", "description": "违约责任条款不公平",
                 "regulation": "合同法", "suggestion": "修改违约责任条款"},
                {"severity": "medium", "description": "管辖权条款不利",
                 "regulation": "民事诉讼法"},
            ],
            "passed_checks": ["合同主体资格", "合同标的合法性", "签章完整性"],
        },
        "report_result": {
            "summary": "本合同总体风险中等偏高...",
            "dimensions": [
                {"name": "合同结构", "score": 85, "comment": "结构完整"},
                {"name": "风险控制", "score": 55, "comment": "风险较高"},
                {"name": "合规性", "score": 72, "comment": "基本合规"},
            ],
            "recommendations": [
                {"priority": "high", "title": "修改违约条款", "description": "将无限责任改为有限责任"},
                {"priority": "medium", "title": "增加仲裁条款", "description": "增加仲裁争议解决机制"},
            ],
            "overall_score": 70,
        },
    }

    # 验证数据结构完整性
    assert result["status"] == "completed"
    assert len(result["steps"]) == 3
    assert result["parse_result"]["document_info"]["type"] == "技术服务合同"
    assert len(result["clause_result"]["clauses"]) == 2
    assert len(result["risk_result"]["risks"]) == 3
    assert result["compliance_result"]["compliance_score"] == 72
    assert result["report_result"]["overall_score"] == 70

    # 验证风险等级分布
    risks = result["risk_result"]["risks"]
    high_count = sum(1 for r in risks if r["level"] == "high")
    medium_count = sum(1 for r in risks if r["level"] == "medium")
    low_count = sum(1 for r in risks if r["level"] == "low")
    assert high_count == 1
    assert medium_count == 1
    assert low_count == 1

    # 验证合规检查数据
    assert len(result["compliance_result"]["issues"]) == 2
    assert len(result["compliance_result"]["passed_checks"]) == 3

    # 验证报告维度
    assert len(result["report_result"]["dimensions"]) == 3
    assert len(result["report_result"]["recommendations"]) == 2


# ============================================================
# 7. 端到端流程测试
# ============================================================

def test_end_to_end_tracking_flow():
    """测试端到端追踪流程"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    start = time.time()

    # 模拟完整审查流程
    steps_sequence = ["init", "parse", "clause", "risk", "compliance", "report", "complete"]

    for step_id in steps_sequence:
        tracker.start_step(step_id, f"正在执行 {step_id}")
        time.sleep(0.01)
        tracker.complete_step(step_id, f"{step_id} 完成")

    tracker.finish()

    # 验证最终状态
    summary = tracker.get_status_summary()
    assert summary["is_complete"] is True
    assert summary["completed"] == 7
    assert summary["failed"] == 0
    assert summary["overall_progress"] == 100
    assert tracker.end_time is not None
    assert tracker.get_total_duration() > 0

    # 验证序列化
    data = tracker.to_dict()
    assert data["overall_progress"] == 100
    for step_data in data["steps"]:
        assert step_data["status"] == "completed"
        assert step_data["duration"] is not None


def test_end_to_end_partial_failure():
    """测试部分失败的端到端流程"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()

    # 正常完成前两步
    tracker.start_step("init")
    tracker.complete_step("init")
    tracker.start_step("parse")
    tracker.complete_step("parse")

    # risk 步骤失败
    tracker.start_step("risk")
    tracker.fail_step("risk", "LLM调用超时")

    # finish 应该完成剩余步骤
    tracker.finish()

    summary = tracker.get_status_summary()
    # finish() 将所有 pending 改为 completed，risk 保持 failed
    # completed: init, parse, clause, compliance, report, complete = 6
    # failed: risk = 1
    # is_complete: 6 + 1 >= 7 = True
    assert summary["completed"] == 6  # init, parse, clause, compliance, report, complete
    assert summary["failed"] == 1  # risk
    assert summary["is_complete"] is True


def test_end_to_end_with_progress_updates():
    """测试带进度更新的端到端流程"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()

    # init 步骤带进度更新
    tracker.start_step("init")
    tracker.update_progress("init", 30, "初始化环境")
    assert tracker.step_states["init"]["progress"] == 30

    tracker.update_progress("init", 70, "加载配置")
    assert tracker.step_states["init"]["progress"] == 70

    tracker.update_progress("init", 100, "初始化完成")
    tracker.complete_step("init")

    assert tracker.step_states["init"]["progress"] == 100
    assert tracker.get_overall_progress() > 0


# ============================================================
# 8. 边界情况测试
# ============================================================

def test_tracker_unknown_step():
    """测试未知步骤ID"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    # 不应抛出异常
    tracker.start_step("nonexistent")
    tracker.complete_step("nonexistent")
    tracker.fail_step("nonexistent")
    tracker.update_progress("nonexistent", 50)


def test_tracker_empty_steps():
    """测试空步骤列表"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker(steps=[])
    progress = tracker.get_overall_progress()
    assert progress == 0, f"空步骤列表进度应为0，实际为{progress}"
    summary = tracker.get_status_summary()
    assert summary["total_steps"] == 0, f"空步骤列表总步骤应为0，实际为{summary['total_steps']}"
    assert summary["completed"] == 0, f"空步骤列表完成数应为0，实际为{summary['completed']}"
    assert summary["is_complete"] is True, f"空步骤列表应标记为完成"


def test_tracker_double_complete():
    """测试重复完成步骤"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker = ReviewProgressTracker()
    tracker.start_step("init")
    tracker.complete_step("init")
    # 重复完成不应抛出异常
    tracker.complete_step("init")
    assert tracker.step_states["init"]["status"] == "completed"


def test_result_data_empty_risks():
    """测试空风险数据"""
    from frontend.components.result_display import _generate_text_summary

    result = {
        "status": "completed",
        "risk_result": {"risks": []},
    }
    summary = _generate_text_summary(result)
    assert "completed" in summary


def test_result_data_missing_fields():
    """测试缺少字段的数据"""
    from frontend.components.result_display import _truncate

    assert _truncate("") == "未知"
    assert _truncate(None) == "未知"
    assert _truncate("abc", 100) == "abc"


# ============================================================
# 9. 多会话隔离测试
# ============================================================

def test_multiple_trackers_isolation():
    """测试多个追踪器隔离"""
    from frontend.components.progress_tracker import ReviewProgressTracker

    tracker1 = ReviewProgressTracker()
    tracker2 = ReviewProgressTracker()

    tracker1.start_step("init")
    tracker1.complete_step("init")
    tracker2.start_step("parse")
    time.sleep(0.01)
    tracker2.complete_step("parse")

    # tracker1 只有 init 完成
    assert tracker1.step_states["init"]["status"] == "completed"
    assert tracker1.step_states["parse"]["status"] == "pending"

    # tracker2 只有 parse 完成
    assert tracker2.step_states["init"]["status"] == "pending"
    assert tracker2.step_states["parse"]["status"] == "completed"


# ============================================================
# 运行所有测试
# ============================================================

def run_all_tests():
    global passed, failed, total
    passed = 0
    failed = 0
    total = 0

    print("\n" + "=" * 60)
    print("🧪 Day 24: 结果展示与交互优化 - 测试套件")
    print("=" * 60)

    print("\n📦 1. 模块导入测试")
    run_test("进度追踪器模块导入", test_progress_tracker_import)
    run_test("结果展示模块导入", test_result_display_import)
    run_test("审查步骤定义完整性", test_review_steps_definition)

    print("\n🔄 2. ReviewProgressTracker 核心逻辑测试")
    run_test("追踪器创建", test_tracker_creation)
    run_test("自定义步骤", test_tracker_custom_steps)
    run_test("开始步骤", test_tracker_start_step)
    run_test("完成步骤", test_tracker_complete_step)
    run_test("失败步骤", test_tracker_fail_step)
    run_test("更新进度", test_tracker_update_progress)
    run_test("总体进度计算", test_tracker_overall_progress)
    run_test("耗时统计", test_tracker_duration)
    run_test("完成整个审查", test_tracker_finish)
    run_test("状态摘要", test_tracker_status_summary)
    run_test("序列化", test_tracker_serialization)
    run_test("自动完成之前的步骤", test_tracker_auto_complete_previous)
    run_test("便捷创建函数", test_create_review_tracker)

    print("\n🔧 3. 格式化函数测试")
    run_test("毫秒级格式化", test_format_duration_milliseconds)
    run_test("秒级格式化", test_format_duration_seconds)
    run_test("分钟级格式化", test_format_duration_minutes)
    run_test("状态emoji映射", test_get_status_emoji)
    run_test("短文本截断", test_truncate_short_text)
    run_test("长文本截断", test_truncate_long_text)

    print("\n📝 4. 文本摘要生成测试")
    run_test("完整数据文本摘要", test_generate_text_summary)
    run_test("最小数据文本摘要", test_generate_text_summary_minimal)
    run_test("完整审查结果摘要", test_generate_text_summary_full_result)

    print("\n⚡ 5. 快速摘要测试")
    run_test("快速摘要渲染", test_render_quick_summary)
    run_test("无风险快速摘要", test_render_quick_summary_no_risks)

    print("\n📊 6. 审查结果数据结构测试")
    run_test("完整结果数据结构验证", test_full_result_structure)

    print("\n🔁 7. 端到端流程测试")
    run_test("端到端追踪流程", test_end_to_end_tracking_flow)
    run_test("部分失败端到端流程", test_end_to_end_partial_failure)
    run_test("带进度更新的端到端流程", test_end_to_end_with_progress_updates)

    print("\n⚠️ 8. 边界情况测试")
    run_test("未知步骤ID", test_tracker_unknown_step)
    run_test("空步骤列表", test_tracker_empty_steps)
    run_test("重复完成步骤", test_tracker_double_complete)
    run_test("空风险数据", test_result_data_empty_risks)
    run_test("缺少字段的数据", test_result_data_missing_fields)

    print("\n🔒 9. 多会话隔离测试")
    run_test("多个追踪器隔离", test_multiple_trackers_isolation)

    # 汇总
    print("\n" + "=" * 60)
    print(f"📊 测试结果: {passed}/{total} 通过, {failed} 失败")
    print("=" * 60)

    if failed == 0:
        print("🎉 所有测试通过！")
    else:
        print(f"⚠️ 有 {failed} 个测试失败")

    return passed, failed, total


if __name__ == "__main__":
    run_all_tests()
