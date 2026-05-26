"""
Skills模块 - 可复用能力模块
"""

from .base_skill import BaseSkill
from .document.pdf_reader import PDFReaderSkill
from .document.docx_parser import DocxParserSkill
from .document.ocr_processor import OCRProcessorSkill
from .skill_registry import SkillRegistry

# 预定义Skills实例
pdf_reader = PDFReaderSkill()
docx_parser = DocxParserSkill()
ocr_processor = OCRProcessorSkill()

# 所有可用Skills
document_skills = [pdf_reader, docx_parser, ocr_processor]

__all__ = [
    "BaseSkill",
    "PDFReaderSkill",
    "DocxParserSkill",
    "OCRProcessorSkill",
    "SkillRegistry",
    "pdf_reader",
    "docx_parser",
    "ocr_processor",
    "document_skills",
]
