"""
文档处理Skills模块
"""

from .pdf_reader import PDFReaderSkill
from .docx_parser import DocxParserSkill
from .ocr_processor import OCRProcessorSkill

__all__ = [
    "PDFReaderSkill",
    "DocxParserSkill",
    "OCRProcessorSkill",
]
