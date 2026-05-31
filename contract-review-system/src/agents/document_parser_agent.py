"""
文档解析Agent模块 - LLM驱动，支持长文本处理
"""
from typing import Any, Dict, List, Optional
import re
import json
import asyncio
import logging
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from .base_agent import BaseAgent
from src.utils.llm_response import extract_llm_content, parse_json_from_llm

logger = logging.getLogger(__name__)

# 尝试导入json_repair，没有则使用内置修复
try:
    import json_repair
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False


class DocumentParserAgent(BaseAgent):
    """
    文档解析Agent（生产级）

    特性：
    - 单次LLM调用提取所有信息
    - 语义分块支持长文本
    - 异步非阻塞调用
    - 数据标准化和验证
    - 重试机制和JSON容错
    """

    def __init__(
        self,
        agent_id: str = "document_parser",
        name: str = "文档解析Agent",
        chunk_size: int = 12000,
        chunk_overlap: int = 500,
        max_retries: int = 3,
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="document_parser",
            description="负责解析合同文档，提取基本信息和结构",
            **kwargs
        )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_retries = max_retries

        logger.info(f"文档解析Agent初始化完成: {name}")

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理解析任务

        Args:
            task: 任务数据
                - contract_text: 合同文本
                - contract_type: 合同类型 (可选)

        Returns:
            解析结果
        """
        contract_text = task.get("contract_text", "")
        specified_type = task.get("contract_type")

        if not contract_text:
            return {"error": "合同文本为空"}

        logger.info(f"开始解析合同，文本长度: {len(contract_text)}")

        # 单次LLM调用提取所有信息
        extraction_result = await self._extract_all_info(contract_text, specified_type)

        if "error" in extraction_result:
            return extraction_result

        # 标准化处理
        standardized = self._standardize_result(extraction_result)

        result = {
            "document_info": {
                "contract_type": standardized["contract_type"],
                "basic_info": standardized["basic_info"],
                "sections_count": len(standardized["sections"]),
                "text_length": len(contract_text),
            },
            "sections": standardized["sections"],
            "dates": standardized["dates"],
            "amounts": standardized["amounts"],
            "parties": standardized["basic_info"].get("parties", []),
            "definitions": standardized.get("definitions", []),
        }

        logger.info(f"合同解析完成，类型: {standardized['contract_type']}，条款数: {len(standardized['sections'])}")
        return result

    async def _extract_all_info(self, text: str, specified_type: str = None) -> Dict[str, Any]:
        """
        单次LLM调用提取所有信息

        Args:
            text: 合同文本
            specified_type: 指定的合同类型

        Returns:
            提取结果
        """
        # 长文本分块处理
        if len(text) > self.chunk_size:
            return await self._map_reduce_extract(text, specified_type)

        # 短文本直接提取
        return await self._llm_extract_all(text, specified_type)

    async def _llm_extract_all(self, text: str, specified_type: str = None) -> Dict[str, Any]:
        """
        使用LLM提取所有信息

        Args:
            text: 合同文本
            specified_type: 指定的合同类型

        Returns:
            提取结果
        """
        type_instruction = ""
        if specified_type:
            type_instruction = f"\n合同类型已指定为: {specified_type}，请直接使用此类型。"

        system_prompt = f"""你是一个专业的合同信息提取助手。请从合同文本中提取所有信息，一次调用完成。

输出格式要求（必须是严格有效的JSON）：
{{
  "basic_info": {{
    "title": "合同标题",
    "contract_number": "合同编号（如有，没有则为null）",
    "signing_place": "签订地点（如有，没有则为null）",
    "parties": ["甲方全称", "乙方全称"],
    "signing_date": "签署日期（YYYY-MM-DD，没有则为null）"
  }},
  "contract_type": "sales/service/lease/labor/nda/partnership/general",
  "sections": [
    {{
      "id": "条款编号（如1或1.1）",
      "title": "条款标题",
      "content": "条款完整内容（保留原文）",
      "level": 1
    }}
  ],
  "dates": [
    {{"raw": "原始文本", "date": "YYYY-MM-DD", "type": "签署/生效/到期/交付/付款/其他"}}
  ],
  "amounts": [
    {{"raw": "原始文本", "value": 数值（统一转换为元）, "currency": "CNY/USD/其他", "type": "总价/单价/付款/违约金/其他"}}
  ],
  "definitions": [
    {{"term": "术语", "definition": "定义内容"}}
  ]
}}{type_instruction}

规则：
1. 金额统一转换为数值（元），中文大写转换为阿拉伯数字
2. 日期统一为YYYY-MM-DD格式
3. 条款要保留完整层级结构和完整内容
4. 提取所有术语定义
5. 如果信息缺失，使用null或空数组
6. 只输出JSON，不要其他内容"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请提取以下合同的所有信息：\n\n{text}")
        ]

        try:
            # 异步调用LLM
            response = await self.llm.ainvoke(messages)
            content = extract_llm_content(response.content)

            # 容错JSON解析
            result = parse_json_from_llm(content)

            if isinstance(result, dict):
                return result
            else:
                return {"error": "LLM返回格式错误"}

        except Exception as e:
            logger.error(f"LLM提取失败: {e}")
            return {"error": str(e)}

    async def _map_reduce_extract(self, text: str, specified_type: str = None) -> Dict[str, Any]:
        """
        Map-Reduce长文本处理

        Args:
            text: 合同文本
            specified_type: 指定的合同类型

        Returns:
            合并后的提取结果
        """
        # 1. 语义分块
        chunks = self._semantic_chunking(text)
        logger.info(f"长文本分块: {len(chunks)}块")

        # 2. Map阶段：并行提取每个块
        tasks = [
            self._extract_from_chunk(chunk, i, len(chunks))
            for i, chunk in enumerate(chunks)
        ]
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. 合并结果
        merged = self._merge_chunk_results(chunk_results)

        # 4. 如果指定了类型，使用指定类型
        if specified_type:
            merged["contract_type"] = specified_type

        return merged

    def _semantic_chunking(self, text: str) -> List[str]:
        """
        语义分块（基于条款边界）

        Args:
            text: 合同文本

        Returns:
            分块列表
        """
        # 基于条款边界分割
        section_pattern = r"(?:第[一二三四五六七八九十百千]+条|[一二三四五六七八九十]+、\s*|\d+\.\d+\s+)"
        splits = re.split(f"(?={section_pattern})", text)

        chunks = []
        current_chunk = ""

        for part in splits:
            if len(current_chunk) + len(part) < self.chunk_size:
                current_chunk += part
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = part

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # 如果分块太小，合并
        if len(chunks) == 1:
            return chunks

        # 添加重叠
        if self.chunk_overlap > 0 and len(chunks) > 1:
            overlapped = [chunks[0]]
            for i in range(1, len(chunks)):
                # 从前一块取overlap
                overlap_text = chunks[i-1][-self.chunk_overlap:]
                overlapped.append(overlap_text + chunks[i])
            chunks = overlapped

        return chunks

    async def _extract_from_chunk(self, chunk: str, chunk_index: int, total_chunks: int) -> Dict[str, Any]:
        """
        从单个块中提取信息

        Args:
            chunk: 文本块
            chunk_index: 块索引
            total_chunks: 总块数

        Returns:
            提取结果
        """
        system_prompt = f"""你是一个专业的合同信息提取助手。这是合同的第{chunk_index + 1}/{total_chunks}部分。

输出格式要求（必须是严格有效的JSON）：
{{
  "basic_info": {{
    "title": "合同标题（如果本块包含标题）",
    "parties": ["甲方名称", "乙方名称"]
  }},
  "sections": [
    {{
      "id": "条款编号",
      "title": "条款标题",
      "content": "条款完整内容",
      "level": 1
    }}
  ],
  "dates": [
    {{"raw": "原始文本", "date": "YYYY-MM-DD", "type": "类型"}}
  ],
  "amounts": [
    {{"raw": "原始文本", "value": 数值, "currency": "CNY", "type": "类型"}}
  ],
  "definitions": [
    {{"term": "术语", "definition": "定义内容"}}
  ]
}}

规则：
1. 只提取本块中的信息
2. 金额统一为数值（元）
3. 只输出JSON"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请提取以下合同片段的信息：\n\n{chunk}")
        ]

        try:
            response = await self.llm.ainvoke(messages)
            content = extract_llm_content(response.content)

            return parse_json_from_llm(content)
        except Exception as e:
            logger.warning(f"块{chunk_index}提取失败: {e}")
            return {
                "basic_info": {},
                "sections": [],
                "dates": [],
                "amounts": [],
                "definitions": []
            }

    def _merge_chunk_results(self, chunk_results: List) -> Dict[str, Any]:
        """
        合并多个块的提取结果

        Args:
            chunk_results: 块结果列表

        Returns:
            合并后的结果
        """
        merged = {
            "basic_info": {"title": "", "parties": []},
            "contract_type": "general",
            "sections": [],
            "dates": [],
            "amounts": [],
            "definitions": []
        }

        seen_parties = set()
        seen_dates = set()

        for result in chunk_results:
            if isinstance(result, Exception):
                continue
            if not isinstance(result, dict):
                continue

            # 合并基本信息
            if "basic_info" in result:
                bi = result["basic_info"]
                if bi.get("title") and not merged["basic_info"]["title"]:
                    merged["basic_info"]["title"] = bi["title"]
                for party in bi.get("parties", []):
                    if party not in seen_parties:
                        seen_parties.add(party)
                        merged["basic_info"]["parties"].append(party)

            # 合并条款
            if "sections" in result:
                merged["sections"].extend(result["sections"])

            # 合并日期（去重）
            if "dates" in result:
                for date in result["dates"]:
                    date_key = date.get("date", "")
                    if date_key and date_key not in seen_dates:
                        seen_dates.add(date_key)
                        merged["dates"].append(date)

            # 合并金额
            if "amounts" in result:
                merged["amounts"].extend(result["amounts"])

            # 合并定义
            if "definitions" in result:
                merged["definitions"].extend(result["definitions"])

        return merged

    def _parse_json_with_repair(self, content: str) -> Any:
        """
        容错JSON解析

        Args:
            content: JSON字符串

        Returns:
            解析结果
        """
        # 清理markdown代码块
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()

        # 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试json_repair
        if HAS_JSON_REPAIR:
            try:
                return json_repair.loads(content)
            except Exception:
                pass

        # 手动修复常见问题
        try:
            # 修复尾部逗号
            fixed = re.sub(r',\s*([}\]])', r'\1', content)
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        logger.warning(f"JSON解析失败，返回原始内容")
        return {"raw_content": content}

    def _standardize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化提取结果

        Args:
            result: 原始提取结果

        Returns:
            标准化后的结果
        """
        standardized = result.copy()

        # 标准化金额
        if "amounts" in standardized:
            standardized["amounts"] = [
                self._standardize_amount(amount)
                for amount in standardized["amounts"]
            ]

        # 标准化日期
        if "dates" in standardized:
            standardized["dates"] = [
                self._standardize_date(date)
                for date in standardized["dates"]
                if self._validate_date(date.get("date", ""))
            ]

        # 确保basic_info结构完整
        if "basic_info" not in standardized:
            standardized["basic_info"] = {"title": "", "parties": []}

        return standardized

    def _standardize_amount(self, amount: Dict[str, Any]) -> Dict[str, Any]:
        """标准化金额"""
        raw = amount.get("raw", "")
        value = amount.get("value", 0)

        # 确保value是数值
        if isinstance(value, str):
            try:
                # 去除千位分隔符
                value = value.replace(",", "").replace("，", "")
                value = float(value)
            except ValueError:
                value = 0

        # 处理单位转换
        if "万元" in raw or "w" in raw.lower():
            if isinstance(value, (int, float)) and value < 10000:
                value = value * 10000
        elif "亿" in raw:
            if isinstance(value, (int, float)) and value < 100000000:
                value = value * 100000000

        amount["value"] = value
        return amount

    def _standardize_date(self, date: Dict[str, Any]) -> Dict[str, Any]:
        """标准化日期"""
        date_str = date.get("date", "")

        # 尝试修复常见格式问题
        if date_str:
            # 处理中文日期格式
            match = re.match(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", date_str)
            if match:
                year, month, day = match.groups()
                date["date"] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        return date

    def _validate_date(self, date_str: str) -> bool:
        """验证日期合法性"""
        if not date_str:
            return False
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False
