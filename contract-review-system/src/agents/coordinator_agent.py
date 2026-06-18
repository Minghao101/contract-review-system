"""
协调器Agent模块 - 处理问候和未知意图
"""
import logging
from typing import Any, Dict, Optional

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class CoordinatorAgent(BaseAgent):
    """
    协调器Agent（简化版）

    职责：
    - 处理问候
    - 处理未知意图
    - 提供帮助信息
    """

    def __init__(
        self,
        agent_id: str = "coordinator",
        name: str = "协调器",
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="coordinator",
            description="处理问候和未知意图",
            **kwargs
        )
        logger.info(f"协调器Agent初始化完成: {name}")

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理任务

        Args:
            task: 任务数据

        Returns:
            处理结果
        """
        self.set_running(True)
        self.update_activity()

        try:
            intent = task.get("intent", {})
            intent_type = intent.get("type", "unknown")
            user_message = task.get("user_message", "")

            # 问候
            if intent_type == "greeting":
                return {
                    "status": "completed",
                    "message": "您好！我是智能合同审查助手，可以帮您：\n"
                              "- 审查合同\n"
                              "- 分析条款\n"
                              "- 评估风险\n"
                              "- 检查合规性\n"
                              "- 生成报告\n\n"
                              "请上传或粘贴合同文本，告诉我您需要什么帮助。"
                }

            # 未知意图
            if intent_type == "unknown":
                return {
                    "status": "completed",
                    "message": f"抱歉，我不太理解您的意思。您可以：\n"
                              "- 上传合同文本进行审查\n"
                              "- 告诉我具体需求（如：评估风险、分析条款）\n"
                              "- 问我关于合同的问题"
                }

            # 默认响应
            return {
                "status": "completed",
                "message": "您好！请问有什么可以帮助您的？"
            }

        finally:
            self.set_running(False)
