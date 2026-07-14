"""
讲解预生成器
============
读 .py → 发给 DeepSeek → 存为 .explanations/xxx.py.json
"""

import os, sys, json, requests

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
OUTPUT_DIR = ".explanations"


# ── 按扩展名选择导师角色和 JSON 结构 ──
LANG_CONFIG = {
    ".py": {
        "role": "Python 代码导师",
        "has_functions": True,
        "hint": "- functions 每个 def 都要有\n",
    },
    ".js": {
        "role": "JavaScript 代码导师",
        "has_functions": True,
        "hint": "- functions 每个 function/箭头函数都要有\n",
    },
    ".html": {
        "role": "前端代码导师（HTML/Jinja2 模板）",
        "has_functions": False,
        "hint": "- outline 列页面结构区块（head/body/脚本/样式），5-15 条\n",
    },
    ".css": {
        "role": "CSS 样式分析专家",
        "has_functions": False,
        "hint": "- outline 列样式分组（布局/颜色/排版/组件），5-15 条\n",
    },
    ".yaml": {
        "role": "YAML 配置文件分析专家",
        "has_functions": False,
        "hint": "- outline 列配置区块，5-10 条\n",
    },
    ".json": {
        "role": "JSON 配置文件分析专家",
        "has_functions": False,
        "hint": "- outline 列配置区块，5-10 条\n",
    },
    ".md": {
        "role": "技术文档分析专家",
        "has_functions": False,
        "hint": "- outline 列文档章节结构，5-15 条\n",
    },
    ".txt": {
        "role": "技术文档分析专家",
        "has_functions": False,
        "hint": "- outline 列文档段落结构，3-10 条\n",
    },
}


def generate(filepath: str) -> dict:
    ext = os.path.splitext(filepath)[1].lower()
    cfg = LANG_CONFIG.get(ext)
    if cfg is None:
        print(f"  [跳过] 不支持的文件类型: {ext}")
        return {}

    with open(filepath, "r", encoding="utf-8") as f:
        code = f.read()

    lines = code.split('\n')
    total_lines = len(lines)

    # 代码加行号，AI 直接引用
    numbered = '\n'.join(f"L{i+1}: {l}" for i, l in enumerate(lines))

    # functions 字段按需出现
    if cfg["has_functions"]:
        func_schema = '"functions": [{"name": "函数名", "line": 行号, "summary": "一句话", "detail": "2-5句详解"}],\n'
    else:
        func_schema = ''

    prompt = (
        f"你是{cfg['role']}。分析这个文件并输出 JSON（不要 markdown）。\n\n"
        'JSON 格式：\n'
        '{\n'
        '  "tech_stack": ["用到的库/技术"],\n'
        '  "outline": [{"title": "区块名 (L1-L5)", "line": 1}],\n'
        + func_schema +
        '  "lines": [{"start": 行号, "end": 行号, "text": "讲解"}]\n'
        '}\n\n'
        "关键规则：\n"
        "- 每行开头的 L数字: 就是行号，直接引用，不要自己数\n"
        + cfg["hint"] +
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

    print(f"正在为 {os.path.basename(filepath)} 生成讲解（{cfg['role']}）...")
    resp = requests.post(DEEPSEEK_URL, headers=headers, json=data, timeout=180)
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[:-3]

    result = json.loads(raw)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    d = os.path.dirname(filepath)
    parent = os.path.basename(d)
    # 测试文件在 tests/ 子目录，往上再取一层
    if parent == 'tests':
        parent = os.path.basename(os.path.dirname(d)) + '_tests'
    fname = os.path.basename(filepath)
    out = os.path.join(OUTPUT_DIR, f"{parent}_{fname}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  已保存: {out}")
    fn_count = len(result.get('functions', []))
    print(f"  大纲 {len(result.get('outline',[]))} 条, 函数 {fn_count} 个, 逐行 {len(result.get('lines',[]))} 条")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python generate_explanation.py <文件路径>")
        sys.exit(1)
    generate(sys.argv[1])
