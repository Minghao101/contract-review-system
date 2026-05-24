"""
API模块 - FastAPI应用和路由
"""

from .main import app
from .routes import router
from .task_manager import TaskManager, RabbitMQConsumer

__all__ = [
    "app",
    "router",
    "TaskManager",
    "RabbitMQConsumer",
]
