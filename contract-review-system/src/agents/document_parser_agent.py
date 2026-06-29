"""
文档解析Agent模块 - LLM驱动，支持长文本处理
"""
from typing import Any, Dict, List, Optional
import re
import json
import asyncio
import logging
from datetime import datetime

from .base_agent import BaseAgent
from .business_events import BusinessEvent
from src.memory.memory_layer import MemoryLayer
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
        # 参数验证
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")

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

        # 设置初始状态
        self.set_running(False)

        logger.info(f"文档解析Agent初始化完成: {name}, chunk_size={chunk_size}")

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理解析任务

        数据来源（优先级）：
        1. 共享内存（事件驱动模式）
        2. task 参数（兼容旧模式）

        Args:
            task: 任务数据（兼容旧模式）

        Returns:
            解析结果
        """
        # 优先从共享内存读取（事件驱动模式）
        contract_text = self.read_shared("contract_text", MemoryLayer.CONTEXT) or ""
        specified_type = self.read_shared("contract_type", MemoryLayer.CONTEXT)

        # 兼容旧模式：从 task 参数读取
        if not contract_text:
            contract_text = task.get("contract_text", "")
        if not specified_type:
            specified_type = task.get("contract_type")

        if not contract_text:
            return {"error": "合同文本为空"}

        # 增量修改分支
        intent_type = self.read_shared("intent_type", MemoryLayer.CONTEXT)
        if intent_type == "modify_contract":
            modify_inst = self.read_shared("modify_instruction", MemoryLayer.ANALYSIS)
            if modify_inst:
                return await self._apply_modify(modify_inst, task)

        # 更新状态
        self.set_running(True)
        self.update_activity()

        try:
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

            # 阶段1：写入共享内存 + 发布事件
            self.write_shared("document_parser", result, MemoryLayer.ANALYSIS, validate=False)
            self.publish_event(BusinessEvent.DOCUMENT_PARSED, {"session_id": task.get("session_id")})
            logger.info(f"已发布事件: {BusinessEvent.DOCUMENT_PARSED}")

            return result
        finally:
            # 确保状态被重置
            self.set_running(False)

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

        user_message = f"请提取以下合同的所有信息：\n\n{text}"

        # 带重试的LLM调用
        for attempt in range(self.max_retries):
            try:
                content = await self.chat(user_message, system_prompt)

                # 容错JSON解析
                result = parse_json_from_llm(content)

                if isinstance(result, dict) and "error" not in result:
                    return result

                logger.warning(f"尝试 {attempt + 1}/{self.max_retries} 失败，重试...")
            except Exception as e:
                logger.warning(f"尝试 {attempt + 1}/{self.max_retries} 异常: {e}")

        return {"error": f"达到最大重试次数 {self.max_retries}"}

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

        user_message = f"请提取以下合同片段的信息：\n\n{chunk}"

        try:
            content = await self.chat(user_message, system_prompt)
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

    # ==================== 增量修改 ====================

    async def _apply_modify(self, instruction: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行增量修改：定位条款 → 替换文本 → 返回更新后的 parsed_result

        Args:
            instruction: 修改指令
            task: 任务数据

        Returns:
            更新后的解析结果
        """
        # 读取已有的解析结果
        existing_result = self.read_shared("document_parser", MemoryLayer.ANALYSIS)
        if not existing_result:
            logger.warning("没有已有的解析结果，先全量解析再执行修改")
            existing_result = await self._full_parse(task)
            if "error" in existing_result:
                return existing_result
            # 全量解析后重新读取（_full_parse 已写入 SharedMemory）
            existing_result = self.read_shared("document_parser", MemoryLayer.ANALYSIS)

        sections = existing_result.get("sections", [])
        if not sections:
            return {"error": "合同条款为空，无法执行修改"}

        action = instruction.get("action", "replace")
        locate_type = instruction.get("locate_type", "clause_number")
        locate_value = instruction.get("locate_value", "")

        logger.info(f"增量修改: action={action}, locate={locate_type}, value={locate_value}")

        # 定位目标条款
        target_section, confidence = self._locate_clause(sections, instruction)

        if target_section is None:
            # 降级：尝试用 LLM 语义定位
            target_section, confidence = await self._locate_clause_by_llm(sections, instruction)

        if target_section is None:
            # insert 操作：用 LLM 决定插入位置并生成条款内容
            if action == "insert":
                result = await self._insert_new_clause(sections, instruction, existing_result, task)
                if not isinstance(result, dict) or "error" not in result:
                    # 修改成功，确保 CONTEXT 层的 contract_text 也更新
                    # 检查 sections 中是否有新条款
                    for s in sections:
                        if s.get("modified"):
                            logger.info(f"[诊断] 新条款: id={s.get('id')}, title={s.get('title')}, content前50字={str(s.get('content', ''))[:50]}")
                    self._update_contract_text_in_context(sections)
                return result
            return {"error": f"无法定位条款: {locate_value}", "sections": sections}

        clause_id = target_section.get("id", "unknown")
        logger.info(f"定位到条款: {clause_id} (confidence={confidence:.2f})")

        # 执行修改
        if action == "replace":
            updated_section = self._replace_clause(target_section, instruction)
        elif action == "delete":
            updated_section = None
        elif action == "insert":
            updated_section = self._insert_clause(target_section, instruction)
        else:
            return {"error": f"不支持的操作: {action}"}

        # 更新 sections 列表
        if action == "delete":
            sections = [s for s in sections if s.get("id") != clause_id]
        elif action == "replace":
            sections = [updated_section if s.get("id") == clause_id else s for s in sections]
        elif action == "insert":
            idx = next((i for i, s in enumerate(sections) if s.get("id") == clause_id), len(sections) - 1)
            sections.insert(idx + 1, updated_section)

        # 构建更新后的结果
        updated_result = existing_result.copy()
        updated_result["sections"] = sections
        updated_result["document_info"]["sections_count"] = len(sections)
        updated_result["updated_clause_id"] = clause_id

        # 写入共享内存
        self.write_shared("document_parser", updated_result, MemoryLayer.ANALYSIS, validate=False)

        # 写入 updated_clause 供下游 Agent 增量分析
        if action == "delete":
            self.write_shared("updated_clause", {"id": clause_id, "action": "deleted"}, MemoryLayer.ANALYSIS, validate=False)
        else:
            self.write_shared("updated_clause", updated_section, MemoryLayer.ANALYSIS, validate=False)

        # 更新 CONTEXT 层的 contract_text（从 sections 重建）
        self._update_contract_text_in_context(sections)

        # 发布事件
        self.publish_event(BusinessEvent.CLAUSE_UPDATED, {
            "session_id": task.get("session_id"),
            "clause_id": clause_id,
            "action": action,
        })

        logger.info(f"增量修改完成: {action} clause {clause_id}")
        return updated_result

    def _locate_clause(self, sections: List[Dict], instruction: Dict[str, Any]) -> tuple:
        """
        双重匹配定位条款

        Args:
            sections: 条款列表
            instruction: 修改指令

        Returns:
            (匹配的条款, 置信度) 或 (None, 0.0)
        """
        locate_type = instruction.get("locate_type", "clause_number")
        locate_value = instruction.get("locate_value", "")

        # 策略1：条款编号精确匹配
        if locate_type == "clause_number":
            for section in sections:
                section_id = section.get("id", "")
                if section_id == locate_value:
                    return section, 1.0
                # 处理中文编号：第三条 → 3
                if self._normalize_clause_number(section_id) == self._normalize_clause_number(locate_value):
                    return section, 0.95

        # 策略2：条款标题模糊匹配
        if locate_type in ("clause_title", "clause_number"):
            for section in sections:
                title = section.get("title", "")
                if locate_value in title or title in locate_value:
                    return section, 0.8

        # 策略3：内容关键词匹配
        for section in sections:
            content = section.get("content", "")
            if locate_value in content:
                return section, 0.6

        return None, 0.0

    def _normalize_clause_number(self, num_str: str) -> str:
        """归一化条款编号"""
        import re
        # 中文数字转阿拉伯数字
        chinese_map = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
                       "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}
        for cn, ar in chinese_map.items():
            if cn in num_str:
                num_str = num_str.replace(cn, ar)
        # 提取数字部分
        match = re.search(r'\d+', num_str)
        return match.group() if match else num_str

    async def _locate_clause_by_llm(self, sections: List[Dict], instruction: Dict[str, Any]) -> tuple:
        """
        用 LLM 语义定位条款（降级策略）

        Args:
            sections: 条款列表
            instruction: 修改指令

        Returns:
            (匹配的条款, 置信度) 或 (None, 0.0)
        """
        sections_summary = "\n".join([
            f"[{s.get('id', '?')}] {s.get('title', '无标题')}: {s.get('content', '')[:80]}"
            for s in sections
        ])

        system_prompt = """你是一个合同条款定位专家。根据用户的修改指令，找出对应的条款。

输出格式要求（必须是严格有效的JSON）：
{"clause_id": "条款编号", "confidence": 0.8}

只输出JSON，不要其他内容"""

        user_message = f"""条款列表：
{sections_summary}

用户修改指令：{instruction.get('locate_value', '')}

请定位目标条款，只输出JSON。"""

        try:
            content = await self.chat(user_message, system_prompt)
            result = parse_json_from_llm(content)

            if isinstance(result, dict):
                clause_id = result.get("clause_id", "")
                confidence = result.get("confidence", 0.5)
                for section in sections:
                    if section.get("id") == clause_id:
                        return section, confidence
        except Exception as e:
            logger.error(f"LLM条款定位失败: {e}")

        return None, 0.0

    def _replace_clause(self, section: Dict[str, Any], instruction: Dict[str, Any]) -> Dict[str, Any]:
        """替换条款内容"""
        old_content = instruction.get("old_content", "")
        new_content = instruction.get("new_content", "")

        updated = section.copy()
        if old_content and old_content in updated.get("content", ""):
            updated["content"] = updated["content"].replace(old_content, new_content)
        else:
            updated["content"] = new_content

        updated["modified"] = True
        return updated

    def _insert_clause(self, target_section: Dict[str, Any], instruction: Dict[str, Any]) -> Dict[str, Any]:
        """在目标条款后插入新条款"""
        new_content = instruction.get("new_content", "")
        target_id = target_section.get("id", "0")

        return {
            "id": f"{target_id}+",
            "title": "新增条款",
            "content": new_content,
            "level": target_section.get("level", 1),
            "modified": True,
        }

    def _update_contract_text_in_context(self, sections: List[Dict[str, Any]]):
        """
        从 sections 重建合同文本并更新 CONTEXT 层

        修改/新增/删除条款后，需要同步更新 CONTEXT 层的 contract_text，
        这样后续追问才能读到修改后的合同内容。
        """
        logger.info(f"重建合同文本: {len(sections)} 个条款")

        # 从 sections 重建完整合同文本
        rebuilt_parts = []
        for section in sections:
            section_id = section.get("id", "")
            title = section.get("title", "")
            content = section.get("content", "")
            if section_id:
                rebuilt_parts.append(f"{section_id} {title}\n{content}")
            elif title:
                rebuilt_parts.append(f"{title}\n{content}")
            else:
                rebuilt_parts.append(content)

        rebuilt_text = "\n\n".join(rebuilt_parts)

        if not rebuilt_text.strip():
            logger.warning("重建的合同文本为空，跳过 CONTEXT 更新")
            return

        logger.info(f"已更新 CONTEXT 层 contract_text（{len(rebuilt_text)}字）")

        # 更新 SharedMemory CONTEXT 层
        self.write_shared("contract_text", rebuilt_text, MemoryLayer.CONTEXT, validate=False)
        logger.info(f"已更新 CONTEXT 层 contract_text（{len(rebuilt_text)}字）")

        # 同步更新 ConversationContext（供 _answer_from_context 使用）
        try:
            from .multi_turn_handler import _current_session_id
            session_id = _current_session_id.get()
            if session_id and session_id != 'default':
                # 通过 handler 的 conversation_manager 更新
                from .multi_turn_handler import MultiTurnHandler
                # 直接找到 conversation_manager 更新 contract_text
                # 这里通过 SharedMemory 已经更新了，_answer_from_context
                # 也会从 SharedMemory 读取，所以不需要额外操作
                logger.info(f"session={session_id} contract_text 已同步更新")
        except Exception as e:
            logger.debug(f"更新 ConversationContext 失败（可忽略）: {e}")

    async def _insert_new_clause(
        self,
        sections: List[Dict],
        instruction: Dict[str, Any],
        existing_result: Dict[str, Any],
        task: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        新增条款（合同中不存在目标条款时的处理）

        用 LLM 分析合同结构，决定插入位置并生成条款内容。

        Args:
            sections: 现有条款列表
            instruction: 修改指令
            existing_result: 已有的解析结果
            task: 任务数据

        Returns:
            更新后的解析结果
        """
        locate_value = instruction.get("locate_value", "")
        new_content_hint = instruction.get("new_content", "")

        # 构建条款摘要供 LLM 决定插入位置
        sections_summary = "\n".join([
            f"[{s.get('id', '?')}] {s.get('title', '无标题')}"
            for s in sections
        ])

        system_prompt = """你是一个合同编辑专家。用户要求在合同中新增一个条款，但合同中没有找到对应的条款。
请根据合同结构决定插入位置，并生成条款内容。

输出格式要求（必须是严格有效的JSON）：
{
  "insert_after_clause_id": "目标条款编号（在该条款后插入）",
  "new_clause": {
    "id": "新条款编号",
    "title": "条款标题",
    "content": "条款完整内容（正式的合同语言）",
    "level": 1
  },
  "confidence": 0.8
}

规则：
1. 根据用户要求的内容，选择最合适的插入位置
2. 例如：责任限制条款通常放在"终止"或"违约责任"之后
3. 新条款内容要符合合同的整体风格和法律要求
4. 只输出JSON"""

        user_message = f"""合同条款结构：
{sections_summary}

用户要求新增的条款：{locate_value}
条款内容提示：{new_content_hint or '无'}

请决定插入位置并生成条款内容，只输出JSON。"""

        try:
            content = await self.chat(user_message, system_prompt)
            result = parse_json_from_llm(content)

            if isinstance(result, dict) and "new_clause" in result:
                new_clause = result["new_clause"]
                insert_after_id = result.get("insert_after_clause_id", "")
                logger.info(f"LLM 生成新条款: id={new_clause.get('id')}, title={new_clause.get('title')}, content={str(new_clause.get('content', ''))[:100]}")

                # 找到插入位置
                insert_idx = len(sections)  # 默认追加到末尾
                for i, s in enumerate(sections):
                    if s.get("id") == insert_after_id:
                        insert_idx = i + 1
                        break

                new_clause["modified"] = True
                sections.insert(insert_idx, new_clause)
                logger.info(f"新条款已插入 sections[{insert_idx}], 当前 sections 数量: {len(sections)}")

                # 更新结果
                updated_result = existing_result.copy()
                updated_result["sections"] = sections
                updated_result["document_info"]["sections_count"] = len(sections)
                updated_result["updated_clause_id"] = new_clause.get("id", "new")

                # 写入共享内存
                self.write_shared("document_parser", updated_result, MemoryLayer.ANALYSIS, validate=False)
                self.write_shared("updated_clause", new_clause, MemoryLayer.ANALYSIS, validate=False)

                # 更新 CONTEXT 层的 contract_text（从 sections 重建）
                self._update_contract_text_in_context(sections)

                self.publish_event(BusinessEvent.CLAUSE_UPDATED, {
                    "session_id": task.get("session_id"),
                    "clause_id": new_clause.get("id", "new"),
                    "action": "insert",
                })

                logger.info(f"新增条款完成: {new_clause.get('id')} 插入到 {insert_after_id} 之后")
                return updated_result

        except Exception as e:
            logger.error(f"LLM新增条款失败: {e}")

        return {"error": f"无法生成新条款: {locate_value}", "sections": sections}

    async def _full_parse(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """全量解析（降级方案）"""
        contract_text = self.read_shared("contract_text", MemoryLayer.CONTEXT) or ""
        specified_type = self.read_shared("contract_type", MemoryLayer.CONTEXT)

        if not contract_text:
            return {"error": "合同文本为空"}

        self.set_running(True)
        self.update_activity()
        try:
            extraction_result = await self._extract_all_info(contract_text, specified_type)
            if "error" in extraction_result:
                return extraction_result
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
            self.write_shared("document_parser", result, MemoryLayer.ANALYSIS, validate=False)
            return result
        finally:
            self.set_running(False)
