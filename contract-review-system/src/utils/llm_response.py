"""
LLM响应处理工具 - 统一处理不同类型的响应内容
"""
import json
from typing import Any, Dict, Optional


def extract_llm_content(response_content: Any) -> str:
    """
    从LLM响应中提取文本内容

    Args:
        response_content: LLM响应的content字段，可能是str/list/dict

    Returns:
        提取的文本字符串
    """
    if isinstance(response_content, str):
        return response_content

    if isinstance(response_content, dict):
        # 尝试常见的键名
        for key in ["text", "content", "output", "response"]:
            if key in response_content:
                val = response_content[key]
                return str(val) if not isinstance(val, str) else val
        # 如果没有找到，返回JSON字符串
        return json.dumps(response_content, ensure_ascii=False)

    if isinstance(response_content, list):
        if not response_content:
            return ""
        first = response_content[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            # 尝试从dict中提取text
            for key in ["text", "content", "output"]:
                if key in first:
                    return str(first[key])
            return json.dumps(first, ensure_ascii=False)
        return str(first)

    return str(response_content)


def parse_json_from_llm(content: str) -> Any:
    """
    从LLM响应文本中解析JSON

    Args:
        content: LLM响应文本

    Returns:
        解析后的JSON对象，失败则返回原始字符串
    """
    # 清理markdown代码块
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    content = content.strip()

    # 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 修复尾部逗号
    import re
    try:
        fixed = re.sub(r',\s*([}\]])', r'\1', content)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    return content
