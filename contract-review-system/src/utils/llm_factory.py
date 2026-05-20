"""
LLM工厂模块 - 用于创建和管理LLM实例
"""
from typing import Optional
from langchain_core.language_models import BaseLLM
from langchain_community.llms import Ollama
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from config.settings import get_settings


class LLMFactory:
    """LLM工厂类"""

    def __init__(self):
        self.settings = get_settings()
        self._llm: Optional[BaseLLM] = None

    def create_llm(self, provider: Optional[str] = None) -> BaseLLM:
        """
        创建LLM实例

        Args:
            provider: LLM提供商 (anthropic/openai/ollama)

        Returns:
            LLM实例
        """
        provider = provider or self.settings.LLM_PROVIDER

        if provider == "anthropic":
            return self._create_anthropic_llm()
        elif provider == "openai":
            return self._create_openai_llm()
        elif provider == "ollama":
            return self._create_ollama_llm()
        else:
            raise ValueError(f"不支持的LLM提供商: {provider}")

    def _create_anthropic_llm(self) -> BaseLLM:
        """创建Anthropic/MIMO模型实例"""
        return ChatAnthropic(
            model=self.settings.LLM_MODEL,
            api_key=self.settings.LLM_API_KEY,
            base_url=self.settings.LLM_API_BASE,
            temperature=self.settings.LLM_TEMPERATURE,
            max_tokens=self.settings.LLM_MAX_TOKENS,
        )

    def _create_openai_llm(self) -> BaseLLM:
        """创建OpenAI模型实例"""
        return ChatOpenAI(
            model=self.settings.LLM_MODEL,
            api_key=self.settings.LLM_API_KEY,
            temperature=self.settings.LLM_TEMPERATURE,
            max_tokens=self.settings.LLM_MAX_TOKENS,
        )

    def _create_ollama_llm(self) -> BaseLLM:
        """创建Ollama模型实例"""
        return Ollama(
            model=self.settings.LLM_MODEL,
            temperature=self.settings.LLM_TEMPERATURE,
        )

    def get_llm(self) -> BaseLLM:
        """获取LLM实例 (单例模式)"""
        if self._llm is None:
            self._llm = self.create_llm()
        return self._llm


# 全局LLM工厂实例
llm_factory = LLMFactory()


def get_llm() -> BaseLLM:
    """获取LLM实例的便捷函数"""
    return llm_factory.get_llm()
