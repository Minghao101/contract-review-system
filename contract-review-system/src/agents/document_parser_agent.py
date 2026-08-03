"""
文档解析Agent模块 - 使用 LangChain 高级抽象（ChatPromptTemplate + structured output）
"""
from typing import Any, Dict, List, Optional
import re
import asyncio
import logging
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate

from .base_agent import BaseAgent
from .business_events import BusinessEvent
from .schemas import (
    DocumentExtractionResult, Section, DateInfo, AmountInfo,
    BasicInfo, Definition, ClauseLocation, InsertClauseResult,
)
from src.memory.memory_layer import MemoryLayer

logger = logging.getLogger(__name__)


class DocumentParserAgent(BaseAgent):
    """
    文档解析Agent（LangChain 高级抽象版）

    使用 ChatPromptTemplate 构建 prompt，with_structured_output 解析结果
    """

    # 输出模型
    output_model = DocumentExtractionResult

    # ==================== Prompt 模板 ====================

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", """你是一个专业的合同信息提取助手。请从合同文本中提取所有信息。

提取规则：
1. 金额统一转换为数值（元），中文大写转换为阿拉伯数字
2. 日期统一为YYYY-MM-DD格式
3. 条款要保留完整层级结构和完整内容
4. 提取所有术语定义
5. 如果信息缺失，使用null或空数组

输出格式要求：只输出严格有效的JSON，不要其他内容。JSON结构如下：
{{"basic_info": {{"title": "合同标题", "contract_number": null, "signing_place": null, "parties": ["甲方全称", "乙方全称"], "signing_date": null}}, "contract_type": "general", "sections": [{{"id": "条款编号", "title": "条款标题", "content": "条款完整内容", "level": 1}}], "dates": [], "amounts": [], "definitions": []}}"""),
        ("human", "请提取以下合同的所有信息：\n\n{contract_text}"),
    ])

    # 分块提取模板
    chunk_template = ChatPromptTemplate.from_messages([
        ("system", """你是一个专业的合同信息提取助手。这是合同的第{chunk_index}/{total_chunks}部分。
只提取本块中的信息，金额统一为数值（元）。"""),
        ("human", "请提取以下合同片段的信息：\n\n{chunk_text}"),
    ])

    # 条款定位模板
    locate_template = ChatPromptTemplate.from_messages([
        ("system", """你是一个合同条款定位专家。根据用户的修改指令，找出对应的条款。
根据 clause_id 在条款列表中找到匹配的条款。"""),
        ("human", """条款列表：
{sections_summary}

用户修改指令：{locate_value}

请定位目标条款。"""),
    ])

    # 新增条款模板
    insert_template = ChatPromptTemplate.from_messages([
        ("system", """你是一个合同编辑专家。用户要求在合同中新增一个条款，但合同中没有找到对应的条款。
请根据合同结构决定插入位置，并生成条款内容。

规则：
1. 根据用户要求的内容，选择最合适的插入位置
2. 例如：责任限制条款通常放在"终止"或"违约责任"之后
3. 新条款内容要符合合同的整体风格和法律要求"""),
        ("human", """合同条款结构：
{sections_summary}

用户要求新增的条款：{locate_value}
条款内容提示：{new_content_hint}

请决定插入位置并生成条款内容。"""),
    ])

    def __init__(
        self,
        agent_id: str = "document_parser",
        name: str = "文档解析Agent",
        chunk_size: int = 12000,
        chunk_overlap: int = 500,
        max_retries: int = 3,
        **kwargs
    ):
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

        self._subscribed_events = [BusinessEvent.TASK_CREATED]
        self.set_running(False)

        logger.info(f"文档解析Agent初始化完成: {name}, chunk_size={chunk_size}")

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """处理解析任务"""
        contract_text = self.read_shared("contract_text", MemoryLayer.CONTEXT) or ""
        specified_type = self.read_shared("contract_type", MemoryLayer.CONTEXT)

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

        self.set_running(True)
        self.update_activity()

        try:
            logger.info(f"开始解析合同，文本长度: {len(contract_text)}")

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

            logger.info(f"合同解析完成，类型: {standardized['contract_type']}，条款数: {len(standardized['sections'])}")

            self.write_shared("document_parser", result, MemoryLayer.ANALYSIS, validate=False)
            self.publish_event(BusinessEvent.DOCUMENT_PARSED, {"session_id": task.get("session_id")})
            logger.info(f"已发布事件: {BusinessEvent.DOCUMENT_PARSED}")

            return result
        finally:
            self.set_running(False)

    async def _extract_all_info(self, text: str, specified_type: str = None) -> Dict[str, Any]:
        """单次LLM调用提取所有信息"""
        if len(text) > self.chunk_size:
            return await self._map_reduce_extract(text, specified_type)
        return await self._llm_extract_all(text, specified_type)

    async def _llm_extract_all(self, text: str, specified_type: str = None) -> Dict[str, Any]:
        """使用 LangChain structured output 提取所有信息（带 fallback）"""
        try:
            result = await self.chat_structured(
                contract_text=text,
            )
            return self._extraction_to_dict(result, specified_type)
        except Exception as e:
            logger.warning(f"Structured output 失败，尝试 fallback: {e}")
            # Fallback：使用原始 chat 方法 + JSON 解析
            try:
                system_prompt = """你是一个专业的合同信息提取助手。请从合同文本中提取所有信息。

输出格式要求（必须是严格有效的JSON）：
{
  "basic_info": {
    "title": "合同标题",
    "contract_number": null,
    "signing_place": null,
    "parties": ["甲方全称", "乙方全称"],
    "signing_date": null
  },
  "contract_type": "general",
  "sections": [
    {
      "id": "条款编号",
      "title": "条款标题",
      "content": "条款完整内容",
      "level": 1
    }
  ],
  "dates": [],
  "amounts": [],
  "definitions": []
}

规则：
1. 金额统一转换为数值（元）
2. 日期统一为YYYY-MM-DD格式
3. 条款要保留完整层级结构和完整内容
4. 只输出JSON，不要其他内容"""

                content = await self.chat(
                    f"请提取以下合同的所有信息：\n\n{text[:8000]}",
                    system_prompt=system_prompt,
                )
                import json
                # 清理 markdown 代码块
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                content = content.strip()
                parsed = json.loads(content)
                # 补充默认值
                parsed.setdefault("basic_info", {"title": "", "parties": []})
                parsed.setdefault("contract_type", "general")
                parsed.setdefault("sections", [])
                parsed.setdefault("dates", [])
                parsed.setdefault("amounts", [])
                parsed.setdefault("definitions", [])
                if specified_type:
                    parsed["contract_type"] = specified_type
                return parsed
            except Exception as e2:
                logger.error(f"Fallback 也失败: {e2}")
                return {"error": f"LLM提取失败: {str(e)}"}

    def _extraction_to_dict(self, result: DocumentExtractionResult, specified_type: str = None) -> Dict[str, Any]:
        """将 Pydantic 模型转换为字典"""
        data = {
            "basic_info": result.basic_info.model_dump(),
            "contract_type": specified_type or result.contract_type,
            "sections": [s.model_dump() for s in result.sections],
            "dates": [d.model_dump() for d in result.dates],
            "amounts": [a.model_dump() for a in result.amounts],
            "definitions": [df.model_dump() for df in result.definitions],
        }
        return data

    async def _map_reduce_extract(self, text: str, specified_type: str = None) -> Dict[str, Any]:
        """Map-Reduce长文本处理"""
        chunks = self._semantic_chunking(text)
        logger.info(f"长文本分块: {len(chunks)}块")

        tasks = [
            self._extract_from_chunk(chunk, i, len(chunks))
            for i, chunk in enumerate(chunks)
        ]
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

        merged = self._merge_chunk_results(chunk_results)

        if specified_type:
            merged["contract_type"] = specified_type

        return merged

    def _semantic_chunking(self, text: str) -> List[str]:
        """语义分块（基于条款边界）"""
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

        if len(chunks) == 1:
            return chunks

        if self.chunk_overlap > 0 and len(chunks) > 1:
            overlapped = [chunks[0]]
            for i in range(1, len(chunks)):
                overlap_text = chunks[i-1][-self.chunk_overlap:]
                overlapped.append(overlap_text + chunks[i])
            chunks = overlapped

        return chunks

    async def _extract_from_chunk(self, chunk: str, chunk_index: int, total_chunks: int) -> Dict[str, Any]:
        """从单个块中提取信息"""
        try:
            result = await self.chat_structured(
                prompt_template=self.chunk_template,
                chunk_index=str(chunk_index + 1),
                total_chunks=str(total_chunks),
                chunk_text=chunk,
            )
            return self._extraction_to_dict(result)
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
        """合并多个块的提取结果"""
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

            if "basic_info" in result:
                bi = result["basic_info"]
                if bi.get("title") and not merged["basic_info"]["title"]:
                    merged["basic_info"]["title"] = bi["title"]
                for party in bi.get("parties", []):
                    if party not in seen_parties:
                        seen_parties.add(party)
                        merged["basic_info"]["parties"].append(party)

            if "sections" in result:
                merged["sections"].extend(result["sections"])

            if "dates" in result:
                for date in result["dates"]:
                    date_key = date.get("date", "")
                    if date_key and date_key not in seen_dates:
                        seen_dates.add(date_key)
                        merged["dates"].append(date)

            if "amounts" in result:
                merged["amounts"].extend(result["amounts"])

            if "definitions" in result:
                merged["definitions"].extend(result["definitions"])

        return merged

    def _standardize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """标准化提取结果"""
        standardized = result.copy()

        if "amounts" in standardized:
            standardized["amounts"] = [
                self._standardize_amount(amount)
                for amount in standardized["amounts"]
            ]

        if "dates" in standardized:
            standardized["dates"] = [
                self._standardize_date(date)
                for date in standardized["dates"]
                if self._validate_date(date.get("date", ""))
            ]

        if "basic_info" not in standardized:
            standardized["basic_info"] = {"title": "", "parties": []}

        return standardized

    def _standardize_amount(self, amount: Dict[str, Any]) -> Dict[str, Any]:
        """标准化金额"""
        raw = amount.get("raw", "")
        value = amount.get("value", 0)

        if isinstance(value, str):
            try:
                value = value.replace(",", "").replace("，", "")
                value = float(value)
            except ValueError:
                value = 0

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

        if date_str:
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
        """执行增量修改"""
        existing_result = self.read_shared("document_parser", MemoryLayer.ANALYSIS)
        if not existing_result:
            logger.warning("没有已有的解析结果，先全量解析再执行修改")
            existing_result = await self._full_parse(task)
            if "error" in existing_result:
                return existing_result
            existing_result = self.read_shared("document_parser", MemoryLayer.ANALYSIS)

        sections = existing_result.get("sections", [])
        if not sections:
            return {"error": "合同条款为空，无法执行修改"}

        action = instruction.get("action", "replace")
        locate_type = instruction.get("locate_type", "clause_number")
        locate_value = instruction.get("locate_value", "")

        logger.info(f"增量修改: action={action}, locate={locate_type}, value={locate_value}")

        target_section, confidence = self._locate_clause(sections, instruction)

        if target_section is None:
            target_section, confidence = await self._locate_clause_by_llm(sections, instruction)

        if target_section is None:
            if action == "insert":
                result = await self._insert_new_clause(sections, instruction, existing_result, task)
                if not isinstance(result, dict) or "error" not in result:
                    for s in sections:
                        if s.get("modified"):
                            logger.info(f"[诊断] 新条款: id={s.get('id')}, title={s.get('title')}, content前50字={str(s.get('content', ''))[:50]}")
                    self._update_contract_text_in_context(sections)
                return result
            return {"error": f"无法定位条款: {locate_value}", "sections": sections}

        clause_id = target_section.get("id", "unknown")
        logger.info(f"定位到条款: {clause_id} (confidence={confidence:.2f})")

        if action == "replace":
            updated_section = self._replace_clause(target_section, instruction)
        elif action == "delete":
            updated_section = None
        elif action == "insert":
            updated_section = self._insert_clause(target_section, instruction)
        else:
            return {"error": f"不支持的操作: {action}"}

        if action == "delete":
            sections = [s for s in sections if s.get("id") != clause_id]
        elif action == "replace":
            sections = [updated_section if s.get("id") == clause_id else s for s in sections]
        elif action == "insert":
            idx = next((i for i, s in enumerate(sections) if s.get("id") == clause_id), len(sections) - 1)
            sections.insert(idx + 1, updated_section)

        updated_result = existing_result.copy()
        updated_result["sections"] = sections
        updated_result["document_info"]["sections_count"] = len(sections)
        updated_result["updated_clause_id"] = clause_id

        self.write_shared("document_parser", updated_result, MemoryLayer.ANALYSIS, validate=False)

        if action == "delete":
            self.write_shared("updated_clause", {"id": clause_id, "action": "deleted"}, MemoryLayer.ANALYSIS, validate=False)
        else:
            self.write_shared("updated_clause", updated_section, MemoryLayer.ANALYSIS, validate=False)

        self._update_contract_text_in_context(sections)

        self.publish_event(BusinessEvent.CLAUSE_UPDATED, {
            "session_id": task.get("session_id"),
            "clause_id": clause_id,
            "action": action,
        })

        logger.info(f"增量修改完成: {action} clause {clause_id}")
        return updated_result

    def _locate_clause(self, sections: List[Dict], instruction: Dict[str, Any]) -> tuple:
        """双重匹配定位条款"""
        locate_type = instruction.get("locate_type", "clause_number")
        locate_value = instruction.get("locate_value", "")

        if locate_type == "clause_number":
            for section in sections:
                section_id = section.get("id", "")
                if section_id == locate_value:
                    return section, 1.0
                if self._normalize_clause_number(section_id) == self._normalize_clause_number(locate_value):
                    return section, 0.95

        if locate_type in ("clause_title", "clause_number"):
            for section in sections:
                title = section.get("title", "")
                if locate_value in title or title in locate_value:
                    return section, 0.8

        for section in sections:
            content = section.get("content", "")
            if locate_value in content:
                return section, 0.6

        return None, 0.0

    def _normalize_clause_number(self, num_str: str) -> str:
        """归一化条款编号"""
        chinese_map = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
                       "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}
        for cn, ar in chinese_map.items():
            if cn in num_str:
                num_str = num_str.replace(cn, ar)
        match = re.search(r'\d+', num_str)
        return match.group() if match else num_str

    async def _locate_clause_by_llm(self, sections: List[Dict], instruction: Dict[str, Any]) -> tuple:
        """用 LangChain structured output 语义定位条款"""
        sections_summary = "\n".join([
            f"[{s.get('id', '?')}] {s.get('title', '无标题')}: {s.get('content', '')[:80]}"
            for s in sections
        ])

        try:
            result = await self.chat_structured(
                prompt_template=self.locate_template,
                sections_summary=sections_summary,
                locate_value=instruction.get("locate_value", ""),
            )

            clause_id = result.clause_id
            confidence = result.confidence
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
        """从 sections 重建合同文本并更新 CONTEXT 层"""
        logger.info(f"重建合同文本: {len(sections)} 个条款")

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
        self.write_shared("contract_text", rebuilt_text, MemoryLayer.CONTEXT, validate=False)

        try:
            from .multi_turn_handler import _current_session_id
            session_id = _current_session_id.get()
            if session_id and session_id != 'default':
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
        """新增条款（合同中不存在目标条款时的处理）"""
        locate_value = instruction.get("locate_value", "")
        new_content_hint = instruction.get("new_content", "")

        sections_summary = "\n".join([
            f"[{s.get('id', '?')}] {s.get('title', '无标题')}"
            for s in sections
        ])

        try:
            result = await self.chat_structured(
                prompt_template=self.insert_template,
                sections_summary=sections_summary,
                locate_value=locate_value,
                new_content_hint=new_content_hint or "无",
            )

            new_clause = {
                "id": result.new_clause.id,
                "title": result.new_clause.title,
                "content": result.new_clause.content,
                "level": result.new_clause.level,
                "modified": True,
            }
            insert_after_id = result.insert_after_clause_id
            logger.info(f"LLM 生成新条款: id={new_clause['id']}, title={new_clause['title']}")

            insert_idx = len(sections)
            for i, s in enumerate(sections):
                if s.get("id") == insert_after_id:
                    insert_idx = i + 1
                    break

            sections.insert(insert_idx, new_clause)
            logger.info(f"新条款已插入 sections[{insert_idx}], 当前 sections 数量: {len(sections)}")

            updated_result = existing_result.copy()
            updated_result["sections"] = sections
            updated_result["document_info"]["sections_count"] = len(sections)
            updated_result["updated_clause_id"] = new_clause.get("id", "new")

            self.write_shared("document_parser", updated_result, MemoryLayer.ANALYSIS, validate=False)
            self.write_shared("updated_clause", new_clause, MemoryLayer.ANALYSIS, validate=False)

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
