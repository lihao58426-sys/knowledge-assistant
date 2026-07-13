"""
讲解预生成器
============
读 .py → 发给 DeepSeek → 存为 .explanations/xxx.py.json
"""

import os, sys, json, requests

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
OUTPUT_DIR = ".explanations"


def generate(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        code = f.read()

    lines = code.split('\n')
    total_lines = len(lines)

    # 代码加行号，AI 直接引用
    numbered = '\n'.join(f"L{i+1}: {l}" for i, l in enumerate(lines))

    # 用普通字符串拼接，避免 f-string 里的三引号打架
    prompt = (
        "你是 Python 代码导师。分析这个文件并输出 JSON（不要 markdown）。\n\n"
        'JSON 格式：\n'
        '{\n'
        '  "tech_stack": ["库名"],\n'
        '  "outline": [{"title": "导入与配置 (L1-L5)", "line": 1}],\n'
        '  "functions": [{"name": "函数名", "line": 行号, "summary": "一句话", "detail": "2-5句详解"}],\n'
        '  "lines": [{"start": 行号, "end": 行号, "text": "讲解"}]\n'
        '}\n\n'
        "关键规则：\n"
        "- 每行开头 L数字: 就是行号，直接引用，不要自己数\n"
        "- outline 列主要模块边界，5-15条\n"
        "- functions 每个 def 都要有\n"
        "- lines 选最重要的行讲解，只讲关键逻辑\n"
        f"\n文件（共{total_lines}行，每行已标号）：\n"
        + numbered
    )

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "只输出 JSON，不要 markdown，不要解释。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2, "max_tokens": 4000,
    }

    print(f"正在为 {os.path.basename(filepath)} 生成讲解...")
    resp = requests.post(DEEPSEEK_URL, headers=headers, json=data, timeout=180)
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[:-3]

    result = json.loads(raw)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # 用项目名_文件名 避免同名覆盖（config.py 出现在多个项目）
    parent = os.path.basename(os.path.dirname(filepath))
    fname = os.path.basename(filepath)
    out = os.path.join(OUTPUT_DIR, f"{parent}_{fname}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  已保存: {out}")
    print(f"  大纲 {len(result.get('outline',[]))} 条, 函数 {len(result.get('functions',[]))} 个, 逐行 {len(result.get('lines',[]))} 条")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python generate_explanation.py <文件路径>")
        sys.exit(1)
    generate(sys.argv[1])
