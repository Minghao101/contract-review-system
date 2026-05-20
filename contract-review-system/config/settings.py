"""
智能合同审查系统 - 配置管理
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置"""

    # 项目路径
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "data"
    LOG_DIR: Path = PROJECT_ROOT / "logs"

    # LLM配置 (MIMO模型)
    LLM_PROVIDER: str = Field(default="anthropic", description="LLM提供商")
    LLM_MODEL: str = Field(default="mimo-v2.5", description="模型名称")
    LLM_API_KEY: Optional[str] = Field(default="tp-c44tgkiwl4rfp501sb73g0wg2v5561k4z49mymgbr51lgkrz", description="API密钥")
    LLM_API_BASE: Optional[str] = Field(default="https://token-plan-cn.xiaomimimo.com/anthropic", description="API基础URL")
    LLM_TEMPERATURE: float = Field(default=0.3, description="温度参数")
    LLM_MAX_TOKENS: int = Field(default=10000, description="最大token数")

    # Redis配置
    REDIS_HOST: str = Field(default="localhost", description="Redis主机")
    REDIS_PORT: int = Field(default=6379, description="Redis端口")
    REDIS_DB: int = Field(default=0, description="Redis数据库")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis密码")

    # 向量数据库配置
    CHROMA_PERSIST_DIRECTORY: Path = PROJECT_ROOT / "chroma_db"
    CHROMA_COLLECTION_NAME: str = Field(default="contract_regulations", description="集合名称")
    EMBEDDING_MODEL: str = Field(default="all-MiniLM-L6-v2", description="嵌入模型")

    # 文档处理配置
    MAX_FILE_SIZE_MB: int = Field(default=50, description="最大文件大小(MB)")
    SUPPORTED_FORMATS: list = Field(default=["pdf", "docx", "txt"], description="支持的文件格式")

    # Agent配置
    MAX_CONCURRENT_AGENTS: int = Field(default=5, description="最大并发Agent数")
    AGENT_TIMEOUT: int = Field(default=300, description="Agent超时时间(秒)")

    # 日志配置
    LOG_LEVEL: str = Field(default="INFO", description="日志级别")
    LOG_FORMAT: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # 合同类型配置
    CONTRACT_TYPES: list = Field(
        default=["劳动合同", "采购合同", "租赁合同", "技术合同", "服务合同"],
        description="支持的合同类型"
    )

    # 必备条款配置
    MANDATORY_CLAUSES: dict = Field(
        default={
            "劳动合同": ["工作内容", "工作地点", "工作时间", "劳动报酬", "社会保险", "劳动保护"],
            "采购合同": ["标的物", "数量", "质量", "价款", "履行期限", "违约责任", "争议解决"],
            "租赁合同": ["租赁物", "租金", "租赁期限", "维修责任", "违约责任", "争议解决"],
            "技术合同": ["项目名称", "技术内容", "技术要求", "验收标准", "知识产权", "保密条款"],
            "服务合同": ["服务内容", "服务期限", "服务费用", "验收标准", "违约责任", "保密条款"],
        },
        description="各合同类型必备条款"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 创建全局设置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings
