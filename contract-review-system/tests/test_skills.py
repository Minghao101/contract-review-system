"""
Skills和Agent工具集成测试
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from src.skills import (
    PDFReaderSkill,
    DocxParserSkill,
    OCRProcessorSkill,
    SkillRegistry,
    document_skills,
)
from src.agents.agent_tools import AgentTools, AgentWithTools
from src.agents import DocumentParserAgent


def test_skills_creation():
    """测试Skills创建"""
    print("测试Skills创建...")

    pdf_reader = PDFReaderSkill()
    docx_parser = DocxParserSkill()
    ocr_processor = OCRProcessorSkill()

    assert pdf_reader.skill_id == "pdf_reader"
    assert docx_parser.skill_id == "docx_parser"
    assert ocr_processor.skill_id == "ocr_processor"

    print(f"  - PDF读取Skill: {pdf_reader.name}")
    print(f"  - Word解析Skill: {docx_parser.name}")
    print(f"  - OCR处理Skill: {ocr_processor.name}")
    print("Skills创建测试通过！")
    return True


def test_skill_registry():
    """测试Skills注册器"""
    print("测试Skills注册器...")

    registry = SkillRegistry()

    # 注册Skills
    for skill in document_skills:
        registry.register_skill(skill)

    # 检查注册结果
    skills = registry.list_skills()
    assert len(skills) == 3

    tools = registry.list_tools()
    assert len(tools) == 3

    print(f"  - 已注册Skills: {len(skills)}")
    print(f"  - 工具名称: {tools}")
    print("Skills注册器测试通过！")
    return True


def test_agent_tools():
    """测试Agent工具管理器"""
    print("测试Agent工具管理器...")

    tools = AgentTools()

    # 检查工具列表
    tool_list = tools.list_tools()
    assert len(tool_list) >= 3

    print(f"  - 可用工具数: {len(tool_list)}")
    print("Agent工具管理器测试通过！")
    return True


def test_agent_with_tools():
    """测试带工具的Agent"""
    print("测试带工具的Agent...")

    agent = DocumentParserAgent()
    tools = AgentTools()
    agent_with_tools = AgentWithTools(agent, tools)

    assert agent_with_tools.agent == agent
    assert agent_with_tools.tools == tools

    print(f"  - Agent: {agent.name}")
    print(f"  - 工具数: {len(tools.list_tools())}")
    print("带工具的Agent测试通过！")
    return True


async def test_skill_execution():
    """测试Skill执行"""
    print("测试Skill执行...")

    # 测试PDF读取（模拟）
    pdf_reader = PDFReaderSkill()
    result = await pdf_reader.execute(file_path="test.pdf")
    # 因为文件不存在，应该返回错误
    assert "error" in result or "page_count" in result

    # 测试OCR处理（模拟）
    ocr = OCRProcessorSkill()
    result = await ocr.execute(image_bytes=b"test")
    assert "text" in result

    print("  - PDF读取: OK")
    print("  - OCR处理: OK")
    print("Skill执行测试通过！")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("开始运行Skills集成测试")
    print("=" * 50)

    tests = [
        test_skills_creation(),
        test_skill_registry(),
        test_agent_tools(),
        test_agent_with_tools(),
        asyncio.run(test_skill_execution()),
    ]

    passed = sum(1 for t in tests if t)

    print("=" * 50)
    print(f"测试完成: {passed}/{len(tests)} 通过")
    print("=" * 50)

    return passed == len(tests)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
