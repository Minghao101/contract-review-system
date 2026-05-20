"""
验证工具模块
"""
from pathlib import Path
from typing import Optional


def validate_contract_type(contract_type: str, supported_types: list) -> bool:
    """
    验证合同类型是否支持

    Args:
        contract_type: 合同类型
        supported_types: 支持的合同类型列表

    Returns:
        是否支持
    """
    return contract_type in supported_types


def validate_file_format(file_path: Path, supported_formats: list) -> bool:
    """
    验证文件格式是否支持

    Args:
        file_path: 文件路径
        supported_formats: 支持的文件格式列表

    Returns:
        是否支持
    """
    file_extension = file_path.suffix.lower().lstrip(".")
    return file_extension in supported_formats


def validate_file_size(file_path: Path, max_size_mb: int) -> bool:
    """
    验证文件大小是否在限制内

    Args:
        file_path: 文件路径
        max_size_mb: 最大文件大小(MB)

    Returns:
        是否在限制内
    """
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    return file_size_mb <= max_size_mb


def validate_api_key(api_key: Optional[str]) -> bool:
    """
    验证API密钥是否有效

    Args:
        api_key: API密钥

    Returns:
        是否有效
    """
    return api_key is not None and len(api_key) > 0
