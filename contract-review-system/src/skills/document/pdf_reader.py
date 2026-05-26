"""
PDF读取Skill - 读取PDF文件并提取文本
"""
from typing import Any, Dict
import os
import logging

from ..base_skill import BaseSkill

logger = logging.getLogger(__name__)


class PDFReaderSkill(BaseSkill):
    """
    PDF读取Skill

    读取PDF文件并提取文本内容
    """

    def __init__(self):
        super().__init__(
            skill_id="pdf_reader",
            name="PDF读取",
            description="读取PDF文件并提取文本内容",
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行PDF读取

        Args:
            **kwargs:
                - file_path: PDF文件路径
                - file_bytes: PDF文件字节（二选一）

        Returns:
            提取的文本内容
        """
        file_path = kwargs.get("file_path")
        file_bytes = kwargs.get("file_bytes")

        if not file_path and not file_bytes:
            return {"error": "请提供file_path或file_bytes"}

        try:
            if file_path:
                return self._read_from_path(file_path)
            else:
                return self._read_from_bytes(file_bytes)
        except Exception as e:
            logger.error(f"PDF读取失败: {e}")
            return {"error": str(e)}

    def _read_from_path(self, file_path: str) -> Dict[str, Any]:
        """从文件路径读取PDF"""
        if not os.path.exists(file_path):
            return {"error": f"文件不存在: {file_path}"}

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        return self._read_from_bytes(file_bytes, file_path)

    def _read_from_bytes(self, file_bytes: bytes, file_path: str = "unknown") -> Dict[str, Any]:
        """从字节读取PDF"""
        try:
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(file_bytes))
            pages = []
            full_text = []

            for i, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                pages.append({
                    "page_number": i + 1,
                    "text": page_text,
                    "char_count": len(page_text),
                })
                full_text.append(page_text)

            return {
                "file_path": file_path,
                "page_count": len(pages),
                "pages": pages,
                "full_text": "\n".join(full_text),
                "total_chars": sum(p["char_count"] for p in pages),
            }

        except ImportError:
            return {"error": "请安装pypdf: pip install pypdf"}
        except Exception as e:
            return {"error": f"PDF解析失败: {str(e)}"}
