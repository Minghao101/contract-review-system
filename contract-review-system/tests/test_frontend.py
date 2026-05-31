"""
前端UI框架测试 - Day 21
测试Streamlit前端组件的结构、导入和核心逻辑
"""
import sys
import os
import importlib
import inspect
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ==================== 辅助函数 ====================

def run_test(test_name, test_func):
    """运行单个测试"""
    try:
        test_func()
        print(f"  ✅ {test_name}")
        return True
    except Exception as e:
        print(f"  ❌ {test_name}: {e}")
        return False


# ==================== 测试用例 ====================

def test_streamlit_import():
    """测试Streamlit是否正确安装"""
    try:
        import streamlit as st
        assert hasattr(st, 'set_page_config')
        assert hasattr(st, 'title')
        assert hasattr(st, 'tabs')
        assert hasattr(st, 'chat_input')
        assert hasattr(st, 'chat_message')
        assert hasattr(st, 'spinner')
        assert hasattr(st, 'progress')
        assert hasattr(st, 'file_uploader')
        assert hasattr(st, 'text_area')
        assert hasattr(st, 'session_state')
    except ImportError:
        raise ImportError("Streamlit未安装，请运行: pip install streamlit")


def test_frontend_module_import():
    """测试前端模块可导入"""
    try:
        from frontend import app
        assert hasattr(app, 'main')
    except ImportError as e:
        raise ImportError(f"前端模块导入失败: {e}")


def test_chat_component_import():
    """测试对话组件可导入"""
    try:
        from frontend.components.chat import render_chat_interface
        assert callable(render_chat_interface)
    except ImportError as e:
        raise ImportError(f"对话组件导入失败: {e}")


def test_file_upload_component_import():
    """测试文件上传组件可导入"""
    try:
        from frontend.components.file_upload import render_file_upload
        assert callable(render_file_upload)
    except ImportError as e:
        raise ImportError(f"文件上传组件导入失败: {e}")


def test_sidebar_component_import():
    """测试侧边栏组件可导入"""
    try:
        from frontend.components.sidebar import render_sidebar
        assert callable(render_sidebar)
    except ImportError as e:
        raise ImportError(f"侧边栏组件导入失败: {e}")


def test_result_display_component_import():
    """测试结果展示组件可导入"""
    try:
        from frontend.components.result_display import render_review_result
        assert callable(render_review_result)
    except ImportError as e:
        raise ImportError(f"结果展示组件导入失败: {e}")


def test_chat_component_functions():
    """测试对话组件的内部函数"""
    import frontend.components.chat as chat_module
    
    # 检查所有必需的内部函数存在
    required_functions = [
        '_render_message',
        '_handle_user_input',
        '_process_contract_review',
        '_process_question',
        '_process_quick_risk',
        '_process_report_generation',
        '_format_review_result',
        '_get_default_sample',
    ]
    
    for func_name in required_functions:
        assert hasattr(chat_module, func_name), f"缺少函数: {func_name}"
        assert callable(getattr(chat_module, func_name)), f"函数不可调用: {func_name}"


def test_file_upload_component_functions():
    """测试文件上传组件的内部函数"""
    import frontend.components.file_upload as upload_module
    
    # 检查内部函数存在
    assert hasattr(upload_module, '_read_uploaded_file')
    assert callable(upload_module._read_uploaded_file)


def test_sidebar_component_functions():
    """测试侧边栏组件的内部函数"""
    import frontend.components.sidebar as sidebar_module
    
    assert hasattr(sidebar_module, '_show_sample_contract')
    assert callable(sidebar_module._show_sample_contract)


def test_format_review_result():
    """测试审查结果格式化函数"""
    from frontend.components.chat import _format_review_result
    
    # 测试空结果
    result = _format_review_result({}, "测试合同")
    assert isinstance(result, str)
    assert "合同审查报告" in result
    
    # 测试完整结果
    full_result = {
        "status": "completed",
        "steps_completed": ["文档解析", "条款分析"],
        "parse_result": {
            "document_info": {
                "type": "技术服务合同",
                "party_a": "甲方公司",
                "party_b": "乙方公司"
            }
        },
        "clause_result": {
            "clauses": [
                {"title": "第一条", "summary": "合同标的"}
            ]
        },
        "risk_result": {
            "risks": [
                {"level": "high", "title": "高风险条款"},
                {"level": "medium", "title": "中风险条款"}
            ]
        },
        "compliance_result": {
            "issues": [
                {"description": "合规问题1"}
            ]
        },
        "report_result": {
            "summary": "综合审查报告摘要"
        }
    }
    
    result = _format_review_result(full_result, "完整合同")
    assert "completed" in result
    assert "文档解析" in result
    assert "条款分析" in result
    assert "风险评估" in result
    assert "合规检查" in result
    assert "综合报告" in result
    assert "高风险条款" in result


def test_format_review_result_with_error():
    """测试带错误的审查结果格式化"""
    from frontend.components.chat import _format_review_result
    
    error_result = {
        "status": "failed",
        "error": "解析失败"
    }
    
    result = _format_review_result(error_result, "错误合同")
    assert "failed" in result
    assert "解析失败" in result


def test_get_default_sample():
    """测试默认示例合同"""
    from frontend.components.chat import _get_default_sample
    
    sample = _get_default_sample()
    assert isinstance(sample, str)
    assert len(sample) > 100
    assert "技术服务合同" in sample
    assert "甲方" in sample
    assert "乙方" in sample


def test_read_uploaded_file_txt():
    """测试TXT文件读取"""
    from frontend.components.file_upload import _read_uploaded_file
    from unittest.mock import MagicMock
    
    # 模拟TXT文件上传
    mock_file = MagicMock()
    mock_file.name = "test.txt"
    mock_file.type = "text/plain"
    mock_file.read.return_value = "测试合同内容".encode("utf-8")
    
    result = _read_uploaded_file(mock_file)
    assert result == "测试合同内容"


def test_read_uploaded_file_unsupported():
    """测试不支持的文件类型"""
    from frontend.components.file_upload import _read_uploaded_file
    from unittest.mock import MagicMock
    
    mock_file = MagicMock()
    mock_file.name = "test.xyz"
    mock_file.type = "application/unknown"
    
    result = _read_uploaded_file(mock_file)
    assert result is None


def test_result_display_render():
    """测试结果展示组件渲染"""
    from frontend.components.result_display import render_review_result
    from unittest.mock import patch, MagicMock
    
    # 测试空记录
    with patch('frontend.components.result_display.st') as mock_st:
        render_review_result({})
        mock_st.markdown.assert_called()


def test_result_display_with_data():
    """测试带数据的结果展示"""
    from frontend.components.result_display import render_review_result
    from unittest.mock import patch
    
    record = {
        "status": "completed",
        "timestamp": "2024-01-01 12:00:00",
        "result": {
            "parse_result": {
                "document_info": {
                    "type": "技术服务合同",
                    "party_a": "甲方",
                    "party_b": "乙方"
                }
            },
            "risk_result": {
                "risks": [
                    {"level": "high", "title": "风险1", "description": "描述1"}
                ]
            }
        }
    }
    
    with patch('frontend.components.result_display.st') as mock_st:
        render_review_result(record)
        assert mock_st.markdown.called


def test_app_main_function():
    """测试主应用入口函数"""
    from frontend.app import main, _render_history_tab, _apply_custom_css
    
    assert callable(main)
    assert callable(_render_history_tab)
    assert callable(_apply_custom_css)


def test_chat_render_function_signature():
    """测试对话组件渲染函数签名"""
    import inspect
    from frontend.components.chat import render_chat_interface
    
    sig = inspect.signature(render_chat_interface)
    # 应该没有必需参数
    for param_name, param in sig.parameters.items():
        assert param.default is not inspect.Parameter.empty or param.kind == inspect.Parameter.VAR_KEYWORD, \
            f"render_chat_interface 不应有必需参数: {param_name}"


def test_file_upload_render_function_signature():
    """测试文件上传组件渲染函数签名"""
    import inspect
    from frontend.components.file_upload import render_file_upload
    
    sig = inspect.signature(render_file_upload)
    for param_name, param in sig.parameters.items():
        assert param.default is not inspect.Parameter.empty or param.kind == inspect.Parameter.VAR_KEYWORD, \
            f"render_file_upload 不应有必需参数: {param_name}"


def test_sidebar_render_function_signature():
    """测试侧边栏组件渲染函数签名"""
    import inspect
    from frontend.components.sidebar import render_sidebar
    
    sig = inspect.signature(render_sidebar)
    for param_name, param in sig.parameters.items():
        assert param.default is not inspect.Parameter.empty or param.kind == inspect.Parameter.VAR_KEYWORD, \
            f"render_sidebar 不应有必需参数: {param_name}"


def test_result_display_render_function_signature():
    """测试结果展示组件渲染函数签名"""
    import inspect
    from frontend.components.result_display import render_review_result
    
    sig = inspect.signature(render_review_result)
    params = list(sig.parameters.keys())
    assert "record" in params, "render_review_result 应接受 record 参数"


def test_frontend_directory_structure():
    """测试前端目录结构完整性"""
    frontend_dir = project_root / "frontend"
    components_dir = frontend_dir / "components"
    
    # 检查目录存在
    assert frontend_dir.exists(), "frontend目录不存在"
    assert components_dir.exists(), "frontend/components目录不存在"
    
    # 检查必需文件
    required_files = [
        "__init__.py",
        "app.py",
    ]
    for f in required_files:
        assert (frontend_dir / f).exists(), f"缺少文件: frontend/{f}"
    
    required_component_files = [
        "__init__.py",
        "chat.py",
        "file_upload.py",
        "sidebar.py",
        "result_display.py",
    ]
    for f in required_component_files:
        assert (components_dir / f).exists(), f"缺少文件: frontend/components/{f}"


def test_chat_module_docstring():
    """测试对话组件模块文档"""
    import frontend.components.chat as chat_module
    assert chat_module.__doc__ is not None
    assert len(chat_module.__doc__) > 0


def test_file_upload_module_docstring():
    """测试文件上传组件模块文档"""
    import frontend.components.file_upload as upload_module
    assert upload_module.__doc__ is not None
    assert len(upload_module.__doc__) > 0


def test_sidebar_module_docstring():
    """测试侧边栏组件模块文档"""
    import frontend.components.sidebar as sidebar_module
    assert sidebar_module.__doc__ is not None
    assert len(sidebar_module.__doc__) > 0


def test_result_display_module_docstring():
    """测试结果展示组件模块文档"""
    import frontend.components.result_display as result_module
    assert result_module.__doc__ is not None
    assert len(result_module.__doc__) > 0


# ==================== 测试运行器 ====================

def run_all_tests():
    """运行所有前端测试"""
    print("\n" + "=" * 60)
    print("📋 Day 21: 前端UI框架测试")
    print("=" * 60)
    
    tests = [
        # 导入测试
        ("Streamlit导入", test_streamlit_import),
        ("前端模块导入", test_frontend_module_import),
        ("对话组件导入", test_chat_component_import),
        ("文件上传组件导入", test_file_upload_component_import),
        ("侧边栏组件导入", test_sidebar_component_import),
        ("结果展示组件导入", test_result_display_component_import),
        
        # 组件函数测试
        ("对话组件内部函数", test_chat_component_functions),
        ("文件上传组件内部函数", test_file_upload_component_functions),
        ("侧边栏组件内部函数", test_sidebar_component_functions),
        
        # 核心逻辑测试
        ("审查结果格式化", test_format_review_result),
        ("带错误的结果格式化", test_format_review_result_with_error),
        ("默认示例合同", test_get_default_sample),
        ("TXT文件读取", test_read_uploaded_file_txt),
        ("不支持文件类型", test_read_uploaded_file_unsupported),
        
        # 渲染测试
        ("结果展示组件渲染", test_result_display_render),
        ("带数据的结果展示", test_result_display_with_data),
        ("主应用入口函数", test_app_main_function),
        
        # 函数签名测试
        ("对话渲染函数签名", test_chat_render_function_signature),
        ("文件上传渲染函数签名", test_file_upload_render_function_signature),
        ("侧边栏渲染函数签名", test_sidebar_render_function_signature),
        ("结果展示渲染函数签名", test_result_display_render_function_signature),
        
        # 结构和文档测试
        ("前端目录结构", test_frontend_directory_structure),
        ("对话组件模块文档", test_chat_module_docstring),
        ("文件上传组件模块文档", test_file_upload_module_docstring),
        ("侧边栏组件模块文档", test_sidebar_module_docstring),
        ("结果展示组件模块文档", test_result_display_module_docstring),
    ]
    
    passed = 0
    failed = 0
    failed_tests = []
    
    for test_name, test_func in tests:
        if run_test(test_name, test_func):
            passed += 1
        else:
            failed += 1
            failed_tests.append(test_name)
    
    print("\n" + "-" * 60)
    print(f"📊 测试结果: {passed}/{passed + failed} 通过")
    
    if failed > 0:
        print(f"\n❌ 失败的测试:")
        for t in failed_tests:
            print(f"  - {t}")
    else:
        print("🎉 全部通过！")
    
    print("=" * 60)
    
    return passed, failed


if __name__ == "__main__":
    passed, failed = run_all_tests()
    sys.exit(0 if failed == 0 else 1)
