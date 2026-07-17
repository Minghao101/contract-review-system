"""
测试 LLM 思考模式 - 两种传递方式对比
方式A: 直接在 payload 中传递 chat_template_kwargs（text_llm_client.py 的方式）
方式B: 通过 LangChain extra_body 传递（llm_factory.py 的方式）
"""
import requests
import json
import sys
import io
import re

# 修复 Windows 终端编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 配置
API_BASE = "http://10.101.106.100:8000/v1"
MODEL = "Intel/Qwen3.5-122B-A10B-int4-AutoRound"
API_KEY = "EMPTY"

# 测试消息
messages = [
    {"role": "user", "content": "1+1等于几？请直接回答数字。"}
]

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def call_api(payload, label):
    """调用 API 并分析结果"""
    print(f"\n{'=' * 60}")
    print(label)
    print(f"{'=' * 60}")

    # 打印实际发送的 payload（隐藏长内容）
    debug_payload = {k: v for k, v in payload.items() if k != "messages"}
    debug_payload["messages"] = f"[{len(payload['messages'])} messages]"
    print(f"发送的payload: {json.dumps(debug_payload, ensure_ascii=False)}")

    resp = requests.post(f"{API_BASE}/chat/completions", json=payload, headers=headers, timeout=120)
    data = resp.json()

    if "error" in data:
        print(f"[ERROR] {data['error']}")
        return None

    if "choices" not in data:
        print(f"[ERROR] 无 choices: {data}")
        return None

    msg = data["choices"][0]["message"]
    content = msg.get("content", "")
    reasoning = msg.get("reasoning_content", None)

    print(f"finish_reason: {data['choices'][0].get('finish_reason')}")
    print(f"回复内容（完整）: {repr(content)}")

    # 检查 reasoning_content 字段
    if reasoning:
        print(f"[WARN] 存在 reasoning_content 字段，长度: {len(reasoning)} 字符")
        print(f"  前200字符: {reasoning[:200]}")
    else:
        print("[OK] 无 reasoning_content 字段")

    # 检查内容中是否内嵌 <think> 标签
    if "<think>" in content:
        think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
        if think_match:
            think_content = think_match.group(1)
            answer = content[think_match.end():].strip()
            print(f"[WARN] 内容包含 <think> 标签，思考长度: {len(think_content)} 字符")
            print(f"  思考前200字: {think_content[:200]}")
            print(f"  最终回答: {repr(answer[:200])}")
        else:
            print(f"[WARN] 内容包含 <think> 但无 </think> 闭合标签")
    elif "</think>" in content:
        print(f"[WARN] 内容包含 </think> 但无 <think> 开始标签")
    else:
        print("[OK] 内容无内嵌思考标签")

    return content


# ============================================================
# 方式A: 直接 payload（text_llm_client.py 的方式）
# ============================================================
print("#" * 60)
print("# 方式A: 直接在 payload 中传递 chat_template_kwargs")
print("#" * 60)

# A1: enable_thinking=False
call_api({
    "model": MODEL,
    "messages": messages,
    "temperature": 0.3,
    "max_tokens": 256,
    "chat_template_kwargs": {"enable_thinking": False},
}, "A1: 直接payload, enable_thinking=False")

# A2: enable_thinking=True
call_api({
    "model": MODEL,
    "messages": messages,
    "temperature": 0.3,
    "max_tokens": 512,
    "chat_template_kwargs": {"enable_thinking": True},
}, "A2: 直接payload, enable_thinking=True")

# A3: 不传 chat_template_kwargs（默认行为）
call_api({
    "model": MODEL,
    "messages": messages,
    "temperature": 0.3,
    "max_tokens": 256,
}, "A3: 直接payload, 不传chat_template_kwargs（默认）")


# ============================================================
# 方式B: LangChain extra_body（llm_factory.py 的方式）
# ============================================================
print("\n\n" + "#" * 60)
print("# 方式B: 模拟 LangChain extra_body 合并到 payload")
print("#" * 60)

# LangChain ChatOpenAI 会把 extra_body 合并到最顶层 payload
# 所以最终效果和方式A是一样的，但这里我们显式测试确认

# B1: enable_thinking=False via extra_body
extra_body_false = {"chat_template_kwargs": {"enable_thinking": False}}
payload_b1 = {
    "model": MODEL,
    "messages": messages,
    "temperature": 0.3,
    "max_tokens": 256,
}
payload_b1.update(extra_body_false)  # 模拟 LangChain 合并 extra_body
call_api(payload_b1, "B1: extra_body模拟, enable_thinking=False")

# B2: enable_thinking=True via extra_body
extra_body_true = {"chat_template_kwargs": {"enable_thinking": True}}
payload_b2 = {
    "model": MODEL,
    "messages": messages,
    "temperature": 0.3,
    "max_tokens": 512,
}
payload_b2.update(extra_body_true)  # 模拟 LangChain 合并 extra_body
call_api(payload_b2, "B2: extra_body模拟, enable_thinking=True")


# ============================================================
# 方式C: 通过 LangChain ChatOpenAI 实际调用
# ============================================================
print("\n\n" + "#" * 60)
print("# 方式C: 实际通过 LangChain ChatOpenAI 调用")
print("#" * 60)

try:
    from langchain_openai import ChatOpenAI

    # C1: enable_thinking=False
    llm_c1 = ChatOpenAI(
        model=MODEL,
        api_key=API_KEY,
        base_url=API_BASE,
        temperature=0.3,
        max_tokens=256,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    resp_c1 = llm_c1.invoke("1+1等于几？请直接回答数字。")
    content_c1 = resp_c1.content
    print(f"\nC1: LangChain ChatOpenAI, enable_thinking=False")
    print(f"回复内容（完整）: {repr(content_c1)}")
    if "<think>" in content_c1:
        print("[WARN] 内容包含 <think> 标签")
    else:
        print("[OK] 内容无内嵌思考标签")

    # C2: enable_thinking=True
    llm_c2 = ChatOpenAI(
        model=MODEL,
        api_key=API_KEY,
        base_url=API_BASE,
        temperature=0.3,
        max_tokens=512,
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )
    resp_c2 = llm_c2.invoke("1+1等于几？请直接回答数字。")
    content_c2 = resp_c2.content
    print(f"\nC2: LangChain ChatOpenAI, enable_thinking=True")
    print(f"回复内容（完整）: {repr(content_c2)}")
    if "<think>" in content_c2:
        think_match = re.search(r'<think>(.*?)</think>', content_c2, re.DOTALL)
        if think_match:
            print(f"[WARN] 内容包含 <think> 标签，思考长度: {len(think_match.group(1))} 字符")
        else:
            print("[WARN] 内容包含 <think> 但无闭合标签")
    else:
        print("[OK] 内容无内嵌思考标签")

except ImportError as e:
    print(f"[SKIP] LangChain 未安装: {e}")
except Exception as e:
    print(f"[ERROR] LangChain 调用失败: {e}")


# ============================================================
# 汇总
# ============================================================
print("\n\n" + "=" * 60)
print("汇总")
print("=" * 60)
print("""
观察要点：
1. 对比 A1 vs A2：直接 payload 方式下 False/True 是否有差异
2. 对比 B1 vs B2：extra_body 模拟方式下是否有差异
3. 对比 A vs B：两种传递方式是否等效
4. 对比 C1 vs C2：LangChain 实际调用是否有差异
5. 关注：reasoning_content 字段、<think> 标签、回复内容长度/内容差异
""")
