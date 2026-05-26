"""
Skills基类 - 定义所有Skills的公共接口
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BaseSkill(ABC):
    """
    Skill基类

    所有Skills都应继承此类并实现抽象方法
    """

    def __init__(
        self,
        skill_id: str,
        name: str,
        description: str,
        version: str = "1.0.0"
    ):
        """
        初始化Skill

        Args:
            skill_id: Skill唯一标识符
            name: Skill名称
            description: Skill描述
            version: 版本号
        """
        self.skill_id = skill_id
        self.name = name
        self.description = description
        self.version = version
        self.created_at = datetime.now()
        self._is_enabled = True

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行Skill（抽象方法）

        Args:
            **kwargs: Skill参数

        Returns:
            执行结果
        """
        pass

    def get_info(self) -> Dict[str, Any]:
        """获取Skill信息"""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "is_enabled": self._is_enabled,
            "created_at": self.created_at.isoformat(),
        }

    def enable(self):
        """启用Skill"""
        self._is_enabled = True
        logger.info(f"Skill已启用: {self.name}")

    def disable(self):
        """禁用Skill"""
        self._is_enabled = False
        logger.info(f"Skill已禁用: {self.name}")

    @property
    def is_enabled(self) -> bool:
        """是否启用"""
        return self._is_enabled
