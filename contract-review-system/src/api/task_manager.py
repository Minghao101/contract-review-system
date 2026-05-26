"""
任务管理器 - 集成RabbitMQ和任务处理
"""
import json
import uuid
from typing import Any, Dict, Optional
from datetime import datetime
import logging

from src.agents.coordinator_agent import CoordinatorAgent
from src.agents import (
    DocumentParserAgent,
    ClauseAnalysisAgent,
    RiskAssessmentAgent,
    ReportGeneratorAgent,
)

logger = logging.getLogger(__name__)


class TaskManager:
    """
    任务管理器

    支持：
    - 异步任务提交（通过RabbitMQ）
    - 同步任务处理
    - 任务状态查询
    """

    def __init__(self, rabbitmq_url: Optional[str] = None):
        """
        初始化任务管理器

        Args:
            rabbitmq_url: RabbitMQ连接地址
        """
        self.rabbitmq_url = rabbitmq_url
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._coordinator = None
        self._init_coordinator()

    def _init_coordinator(self):
        """初始化协调器和Agent"""
        self._coordinator = CoordinatorAgent()

        # 注册Agent
        self._coordinator.register_agent(DocumentParserAgent())
        self._coordinator.register_agent(ClauseAnalysisAgent())
        self._coordinator.register_agent(RiskAssessmentAgent())
        self._coordinator.register_agent(ReportGeneratorAgent())

    async def submit_task(
        self,
        contract_text: str,
        contract_type: str = "general",
        review_focus: list = None,
        callback_url: Optional[str] = None,
    ) -> str:
        """
        提交任务到队列

        Args:
            contract_text: 合同文本
            contract_type: 合同类型
            review_focus: 审查重点
            callback_url: 回调URL

        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())

        # 创建任务记录
        self._tasks[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "contract_type": contract_type,
            "created_at": datetime.now().isoformat(),
            "result": None,
            "error": None,
        }

        # 构建消息
        message = {
            "task_id": task_id,
            "contract_text": contract_text,
            "contract_type": contract_type,
            "review_focus": review_focus or [],
            "callback_url": callback_url,
        }

        # 发送到RabbitMQ
        if self.rabbitmq_url:
            await self._send_to_rabbitmq(message)
        else:
            # 无RabbitMQ时直接处理
            logger.info("无RabbitMQ，直接处理任务")
            await self._process_task_direct(task_id, message)

        return task_id

    async def _send_to_rabbitmq(self, message: Dict[str, Any]):
        """发送消息到RabbitMQ"""
        try:
            import aio_pika

            connection = await aio_pika.connect_robust(self.rabbitmq_url)
            channel = await connection.channel()

            # 声明队列
            queue = await channel.declare_queue("contract_review", durable=True)

            # 发布消息
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(message, ensure_ascii=False).encode(),
                    content_type="application/json",
                ),
                routing_key="contract_review",
            )

            await connection.close()
            logger.info(f"消息已发送到RabbitMQ: {message['task_id']}")

        except Exception as e:
            logger.error(f"发送到RabbitMQ失败: {e}")
            # 降级为直接处理
            await self._process_task_direct(message["task_id"], message)

    async def _process_task_direct(self, task_id: str, message: Dict[str, Any]):
        """直接处理任务（无队列）"""
        self._tasks[task_id]["status"] = "processing"

        try:
            result = await self._coordinator.process({
                "contract_text": message["contract_text"],
                "contract_type": message.get("contract_type", "general"),
                "review_focus": message.get("review_focus", []),
            })

            self._tasks[task_id]["status"] = "completed"
            self._tasks[task_id]["result"] = result

        except Exception as e:
            self._tasks[task_id]["status"] = "failed"
            self._tasks[task_id]["error"] = str(e)
            logger.error(f"任务处理失败: {e}")

    async def process_sync(
        self,
        contract_text: str,
        contract_type: str = "general",
        review_focus: list = None,
    ) -> Dict[str, Any]:
        """
        同步处理任务

        Args:
            contract_text: 合同文本
            contract_type: 合同类型
            review_focus: 审查重点

        Returns:
            审查结果
        """
        result = await self._coordinator.process({
            "contract_text": contract_text,
            "contract_type": contract_type,
            "review_focus": review_focus or [],
        })
        return result

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        return self._tasks.get(task_id)

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 10
    ) -> list:
        """列出任务"""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        return sorted(tasks, key=lambda x: x["created_at"], reverse=True)[:limit]


class RabbitMQConsumer:
    """
    RabbitMQ消费者

    监听队列并处理任务
    """

    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.task_manager = TaskManager(rabbitmq_url)

    async def start_consuming(self):
        """开始消费消息"""
        try:
            import aio_pika

            connection = await aio_pika.connect_robust(self.rabbitmq_url)
            channel = await connection.channel()

            queue = await channel.declare_queue("contract_review", durable=True)

            logger.info("开始监听contract_review队列...")

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        body = json.loads(message.body.decode())
                        task_id = body.get("task_id")
                        logger.info(f"收到任务: {task_id}")

                        await self.task_manager._process_task_direct(task_id, body)
                        logger.info(f"任务完成: {task_id}")

        except Exception as e:
            logger.error(f"消费者启动失败: {e}")
            raise
