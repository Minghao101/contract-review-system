"""
测试 MIMO 流式输出
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from openai import OpenAI

API_KEY = "tp-c44tgkiwl4rfp501sb73g0wg2v5561k4z49mymgbr51lgkrz"
BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
MODEL = "mimo-v2.5"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

print("=" * 60)
print("测试1: stream=True (OpenAI SDK)")
print("=" * 60)

try:
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": "1+1等于几？请用一句话回答。"}
        ],
        max_tokens=100,
        temperature=0.3,
        stream=True,
    )

    print("流式输出: ", end="", flush=True)
    full_content = ""
    for event in completion:
        # 打印原始事件用于调试
        if event.choices and event.choices[0].delta:
            delta = event.choices[0].delta
            if hasattr(delta, 'content') and delta.content:
                print(delta.content, end="", flush=True)
                full_content += delta.content
            elif hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                print(f"[reasoning: {delta.reasoning_content[:50]}...]", end="", flush=True)
    print()
    if full_content:
        print(f"[OK] 流式输出正常，内容长度: {len(full_content)}")
    else:
        print("[WARN] 流式输出为空")
except Exception as e:
    print(f"\n[ERROR] {e}")

print()
print("=" * 60)
print("测试1b: 原始 SSE 数据")
print("=" * 60)

try:
    import requests
    resp = requests.post(
        f"{BASE_URL}/chat/completions",
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": "1+1等于几？"}],
            "max_tokens": 100,
            "stream": True,
        },
        headers={"Authorization": f"Bearer {API_KEY}"},
        stream=True,
        timeout=30,
    )
    print(f"HTTP Status: {resp.status_code}")
    print("SSE 数据:")
    for line in resp.iter_lines(decode_unicode=True):
        if line:
            print(f"  {line}")
            if line.startswith("data: ") and line != "data: [DONE]":
                import json
                data = json.loads(line[6:])
                if "choices" in data and data["choices"]:
                    delta = data["choices"][0].get("delta", {})
                    if "content" in delta:
                        print(f"    -> content: {delta['content']}")
except Exception as e:
    print(f"[ERROR] {e}")

print()
print("=" * 60)
print("测试2: stream=False (对比)")
print("=" * 60)

try:
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": "1+1等于几？请用一句话回答。"}
        ],
        max_tokens=100,
        temperature=0.3,
        stream=False,
    )
    print(f"回复: {completion.choices[0].message.content}")
    print("[OK] 非流式输出正常")
except Exception as e:
    print(f"[ERROR] {e}")

print()
print("=" * 60)
print("测试3: 关闭思考的各种方法")
print("=" * 60)

test_cases = [
    ("reasoning_effort=low", {"reasoning_effort": "low"}),
    ("reasoning_effort=medium", {"reasoning_effort": "medium"}),
    ("reasoning=false", {"reasoning": False}),
    ("reasoning={}", {"reasoning": {}}),
    ("reasoning={enabled:false}", {"reasoning": {"enabled": False}}),
    ("thinking=false", {"thinking": False}),
    ("chat_template_kwargs={enable_thinking:false}", {"chat_template_kwargs": {"enable_thinking": False}}),
]

for name, extra in test_cases:
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "1+1等于几？用一句话回答。"}],
            max_tokens=100,
            temperature=0.3,
            stream=False,
            extra_body=extra,
        )
        content = completion.choices[0].message.content
        reasoning = getattr(completion.choices[0].message, 'reasoning_content', None)
        print(f"{name}: content={repr(content[:30] if content else None)}, reasoning={'有' if reasoning else '无'}")
    except Exception as e:
        print(f"{name}: [ERROR] {str(e)[:60]}")
