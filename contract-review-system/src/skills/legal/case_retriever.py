"""
案例检索Skill - 检索相关法律案例和判例
"""
from typing import Any, Dict, List, Optional
import logging

from ..base_skill import BaseSkill

logger = logging.getLogger(__name__)


class CaseRetrieverSkill(BaseSkill):
    """
    案例检索Skill

    功能：
    - 根据合同条款类型检索相关案例
    - 提供案例摘要和判决要点
    - 匹配风险场景与历史案例
    """

    # 预置案例库（示例数据，实际应接入法律数据库API）
    CASE_DATABASE = [
        {
            "case_id": "case_001",
            "title": "XX公司诉YY公司合同纠纷案",
            "category": "违约责任",
            "keywords": ["违约金", "过高", "调整"],
            "summary": "法院认定合同约定的违约金过高（超过实际损失的30%），依法调整为实际损失的30%。",
            "judgment": "违约金应以实际损失为基础，兼顾合同履行情况等因素综合确定。",
            "reference": "《民法典》第585条",
            "risk_level": "high",
        },
        {
            "case_id": "case_002",
            "title": "张某诉某科技公司劳动合同纠纷",
            "category": "劳动争议",
            "keywords": ["加班费", "劳动时间", "加班"],
            "summary": "公司未支付加班费，法院判决公司支付加班费及经济补偿。",
            "judgment": "用人单位不得免除支付加班费的法定义务。",
            "reference": "《劳动法》第44条",
            "risk_level": "high",
        },
        {
            "case_id": "case_003",
            "title": "某消费者诉某电商平台格式条款纠纷",
            "category": "格式条款",
            "keywords": ["格式条款", "免责", "消费者"],
            "summary": "电商平台'一经售出概不退换'的格式条款被认定无效。",
            "judgment": "格式条款排除消费者主要权利的，该条款无效。",
            "reference": "《消费者权益保护法》第26条",
            "risk_level": "medium",
        },
        {
            "case_id": "case_004",
            "title": "某软件公司知识产权归属纠纷",
            "category": "知识产权",
            "keywords": ["知识产权", "归属", "委托开发"],
            "summary": "委托开发合同未明确约定知识产权归属，法院判定归受托方所有。",
            "judgment": "委托开发完成的发明创造，除当事人另有约定外，申请专利的权利属于研究开发人。",
            "reference": "《民法典》第859条",
            "risk_level": "medium",
        },
        {
            "case_id": "case_005",
            "title": "某租赁合同纠纷案",
            "category": "租赁合同",
            "keywords": ["租赁", "维修", "责任"],
            "summary": "出租方未履行维修义务，法院判决减免租金。",
            "judgment": "出租人应当履行租赁物的维修义务，但当事人另有约定的除外。",
            "reference": "《民法典》第712条",
            "risk_level": "low",
        },
        {
            "case_id": "case_006",
            "title": "某采购合同标的物质量纠纷",
            "category": "买卖合同",
            "keywords": ["质量", "验收", "标的物"],
            "summary": "买方未在约定期间内提出质量异议，视为交付的标的物质量符合约定。",
            "judgment": "买受人应当在检验期间内将标的物的数量或者质量不符合约定的情形通知出卖人。",
            "reference": "《民法典》第621条",
            "risk_level": "medium",
        },
        {
            "case_id": "case_007",
            "title": "某保密协议纠纷案",
            "category": "保密条款",
            "keywords": ["保密", "竞业限制", "补偿"],
            "summary": "公司约定了竞业限制但未支付补偿金，法院判定竞业限制条款对劳动者不产生约束力。",
            "judgment": "用人单位与劳动者约定竞业限制，应在竞业限制期限内按月给予劳动者经济补偿。",
            "reference": "《劳动合同法》第23条",
            "risk_level": "high",
        },
        {
            "case_id": "case_008",
            "title": "某仲裁条款效力纠纷",
            "category": "争议解决",
            "keywords": ["仲裁", "诉讼", "管辖"],
            "summary": "合同同时约定仲裁和诉讼，仲裁条款被认定无效。",
            "judgment": "当事人约定争议可以向仲裁机构申请仲裁也可以向人民法院起诉的，仲裁协议无效。",
            "reference": "《仲裁法》第5条",
            "risk_level": "medium",
        },
    ]

    def __init__(self):
        super().__init__(
            skill_id="case_retriever",
            name="案例检索",
            description="根据合同条款类型检索相关法律案例和判例",
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行案例检索

        Args:
            **kwargs:
                - query: 搜索关键词（可选）
                - category: 案例类别（可选）
                - risk_level: 风险等级筛选（可选）
                - keywords: 关键词列表（可选）

        Returns:
            检索结果
        """
        query = kwargs.get("query", "")
        category = kwargs.get("category", "")
        risk_level = kwargs.get("risk_level", "")
        keywords = kwargs.get("keywords", [])

        try:
            results = self._search_cases(
                query=query,
                category=category,
                risk_level=risk_level,
                keywords=keywords,
            )

            return {
                "total_found": len(results),
                "cases": results,
                "search_params": {
                    "query": query,
                    "category": category,
                    "risk_level": risk_level,
                    "keywords": keywords,
                },
            }
        except Exception as e:
            logger.error(f"案例检索失败: {e}")
            return {"error": str(e)}

    def _search_cases(
        self,
        query: str = "",
        category: str = "",
        risk_level: str = "",
        keywords: List[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        搜索案例

        Args:
            query: 搜索关键词
            category: 案例类别
            risk_level: 风险等级
            keywords: 关键词列表

        Returns:
            匹配的案例列表
        """
        results = []
        keywords = keywords or []

        for case in self.CASE_DATABASE:
            # 类别过滤
            if category and case["category"] != category:
                continue

            # 风险等级过滤
            if risk_level and case["risk_level"] != risk_level:
                continue

            # 关键词匹配评分
            score = 0
            if query:
                # 标题匹配
                if query in case["title"]:
                    score += 3
                # 摘要匹配
                if query in case["summary"]:
                    score += 2
                # 关键词匹配
                for kw in case["keywords"]:
                    if query in kw or kw in query:
                        score += 1

            # 用户关键词匹配
            for kw in keywords:
                if kw in case["summary"] or kw in case["title"]:
                    score += 1
                for case_kw in case["keywords"]:
                    if kw in case_kw:
                        score += 2

            # 如果有匹配分数，或者没有设置过滤条件则返回
            if score > 0 or (not query and not category and not risk_level and not keywords):
                results.append({**case, "match_score": score})

        # 按匹配分数排序
        results.sort(key=lambda x: x["match_score"], reverse=True)

        return results

    def get_cases_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按类别获取案例"""
        return [c for c in self.CASE_DATABASE if c["category"] == category]

    def get_high_risk_cases(self) -> List[Dict[str, Any]]:
        """获取高风险案例"""
        return [c for c in self.CASE_DATABASE if c["risk_level"] == "high"]

    def get_case_by_id(self, case_id: str) -> Optional[Dict[str, Any]]:
        """按ID获取案例"""
        for case in self.CASE_DATABASE:
            if case["case_id"] == case_id:
                return case
        return None
