"""
任务管理器 - 集成RabbitMQ持久化和任务处理
"""
import json
import uuid
from typing import Any, Dict, Optional
from datetime import datetime
from pathlib import Path
import logging

from src.agents.coordinator_agent import CoordinatorAgent
from src.agents import (
    DocumentParserAgent,
    ClauseAnalysisAgent,
    RiskAssessmentAgent,
    ComplianceCheckerAgent,
    ReportGeneratorAgent,
)
from config.settings import settings, get_rabbitmq_url

logger = logging.getLogger(__name__)


class TaskPersistence:
    """
    任务持久化管理

    支持文件持久化，确保任务状态在重启后恢复
    """

    def __init__(self, persist_dir: Optional[Path] = None):
        self.persist_dir = persist_dir or settings.DATA_DIR / "tasks"
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self.persist_dir / "task_index.json"
        self._index: Dict[str, str] = self._load_index()

    def _load_index(self) -> Dict[str, str]:
        """加载任务索引"""
        if self._index_file.exists():
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_index(self):
        """保存任务索引"""
        with open(self._index_file, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False)

    def save_task(self, task_id: str, task_data: Dict[str, Any]):
        """保存任务到文件"""
        task_file = self.persist_dir / f"{task_id}.json"
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(task_data, f, ensure_ascii=False, default=str)
        self._index[task_id] = task_data.get("status", "unknown")
        self._save_index()

    def load_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """从文件加载任务"""
        task_file = self.persist_dir / f"{task_id}.json"
        if task_file.exists():
            with open(task_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def update_task_status(self, task_id: str, status: str, result: Any = None, error: str = None):
        """更新任务状态"""
        task_data = self.load_task(task_id)
        if task_data:
            task_data["status"] = status
            task_data["updated_at"] = datetime.now().isoformat()
            if result is not None:
                task_data["result"] = result
            if error is not None:
                task_data["error"] = error
            self.save_task(task_id, task_data)

    def list_tasks(self, status: Optional[str] = None, limit: int = 10) -> list:
        """列出任务"""
        tasks = []
        for task_id, task_status in self._index.items():
            if status and task_status != status:
                continue
            task_data = self.load_task(task_id)
            if task_data:
                tasks.append(task_data)
        tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return tasks[:limit]


class TaskManager:
    """
    任务管理器

    支持：
    - 异步任务提交（通过RabbitMQ持久化队列）
    - 同步任务处理
    - 任务状态持久化
    """

    def __init__(self, rabbitmq_url: Optional[str] = None):
        """
        初始化任务管理器

        Args:
            rabbitmq_url: RabbitMQ连接地址，为None时使用配置文件
        """
        self.rabbitmq_url = rabbitmq_url or get_rabbitmq_url()
        self.persistence = TaskPersistence()
        self._coordinator = None
        self._init_coordinator()

    def _init_coordinator(self):
        """初始化协调器和Agent"""
        self._coordinator = CoordinatorAgent()

        # 注册Agent
        self._coordinator.register_agent(DocumentParserAgent())
        self._coordinator.register_agent(ClauseAnalysisAgent())
        self._coordinator.register_agent(RiskAssessmentAgent())
        self._coordinator.register_agent(ComplianceCheckerAgent())
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

        # 创建任务记录并持久化
        task_data = {
            "task_id": task_id,
            "status": "queued",
            "contract_type": contract_type,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "result": None,
            "error": None,
        }
        self.persistence.save_task(task_id, task_data)

        # 构建消息
        message = {
            "task_id": task_id,
            "contract_text": contract_text,
            "contract_type": contract_type,
            "review_focus": review_focus or [],
            "callback_url": callback_url,
        }

        # 发送到RabbitMQ（带持久化）
        try:
            await self._send_to_rabbitmq(message)
        except Exception as e:
            logger.error(f"发送到RabbitMQ失败，降级为直接处理: {e}")
            await self._process_task_direct(task_id, message)

        return task_id

    async def _send_to_rabbitmq(self, message: Dict[str, Any]):
        """
        发送消息到RabbitMQ（带持久化）

        - 消息持久化：delivery_mode=2
        - 队列持久化：durable=True
        """
        import aio_pika

        connection = await aio_pika.connect_robust(self.rabbitmq_url)
        channel = await connection.channel()

        # 声明持久化队列
        await channel.declare_queue(
            settings.RABBITMQ_QUEUE,
            durable=True,  # 队列持久化
            arguments={
                "x-message-ttl": 86400000,  # 消息TTL: 24小时
                "x-dead-letter-exchange": "",  # 死信交换机
                "x-dead-letter-routing-key": f"{settings.RABBITMQ_QUEUE}_dlq",  # 死信队列
            }
        )

        # 发布持久化消息
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(message, ensure_ascii=False).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,  # 消息持久化
                message_id=message["task_id"],
                timestamp=datetime.now(),
            ),
            routing_key=settings.RABBITMQ_QUEUE,
        )

        await connection.close()
        logger.info(f"持久化消息已发送到RabbitMQ: {message['task_id']}")

    async def _process_task_direct(self, task_id: str, message: Dict[str, Any]):
        """直接处理任务（无队列或降级时）"""
        self.persistence.update_task_status(task_id, "processing")

        try:
            result = await self._coordinator.process({
                "contract_text": message["contract_text"],
                "contract_type": message.get("contract_type", "general"),
                "review_focus": message.get("review_focus", []),
            })

            self.persistence.update_task_status(task_id, "completed", result=result)

        except Exception as e:
            self.persistence.update_task_status(task_id, "failed", error=str(e))
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
        """获取任务状态（从持久化存储）"""
        return self.persistence.load_task(task_id)

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 10
    ) -> list:
        """列出任务（从持久化存储）"""
        return self.persistence.list_tasks(status=status, limit=limit)


class RabbitMQConsumer:
    """
    RabbitMQ消费者

    监听持久化队列并处理任务
    """

    def __init__(self, rabbitmq_url: Optional[str] = None):
        self.rabbitmq_url = rabbitmq_url or get_rabbitmq_url()
        self.task_manager = TaskManager(self.rabbitmq_url)

    async def start_consuming(self):
        """开始消费消息"""
        import aio_pika

        connection = await aio_pika.connect_robust(self.rabbitmq_url)
        channel = await connection.channel()

        # 设置预取数量（每次只处理1条消息）
        await channel.set_qos(prefetch_count=1)

        # 声明持久化队列
        queue = await channel.declare_queue(
            settings.RABBITMQ_QUEUE,
            durable=True
        )

        # 声明死信队列
        await channel.declare_queue(
            f"{settings.RABBITMQ_QUEUE}_dlq",
            durable=True
        )

        logger.info(f"开始监听 {settings.RABBITMQ_QUEUE} 队列...")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        body = json.loads(message.body.decode())
                        task_id = body.get("task_id")
                        logger.info(f"收到任务: {task_id}")

                        await self.task_manager._process_task_direct(task_id, body)
                        logger.info(f"任务完成: {task_id}")

                    except Exception as e:
                        logger.error(f"处理消息失败: {e}")
                        # 消息会被重新入队或进入死信队列
                        raise


# 全局任务管理器实例
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """获取全局任务管理器"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
