"""验证新切分策略——对比新旧 chunk 数 + 抽查切分质量"""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from index import _chunk_simple, chunk_text

test_files = [
    ("rag_engine.py", "Python"),
    ("server.py", "Python"),
    ("../TO DO/知识点总结-Docker完整指南-从安装到构建.md", "Markdown"),
    ("../TO DO/知识点总结-Redis.md", "Markdown"),
    ("../pos_daily_report/config.yaml", "YAML（应走simple）"),
]

print("=" * 60)
print("新旧切分效果对比")
print("=" * 60)

for path, ftype in test_files:
    full = os.path.join(os.path.dirname(__file__), path)
    if not os.path.exists(full):
        print(f"{ftype} {path}: 文件不存在跳过")
        continue
    with open(full, "r", encoding="utf-8") as f:
        text = f.read()
    old_n = len(_chunk_simple(text, path))
    new_n = len(chunk_text(text, path))
    change = "+" if new_n > old_n else ("-" if new_n < old_n else "=")
    print(f"{ftype:8s} | 旧:{old_n:3d} → 新:{new_n:3d} ({change}) | {os.path.basename(path)}")

print("\n" + "=" * 60)
print("抽查：rag_engine.py 第一个 chunk 是否在函数边界")
print("=" * 60)
with open("rag_engine.py", "r", encoding="utf-8") as f:
    text = f.read()
chunks = chunk_text(text, "rag_engine.py")
for i, c in enumerate(chunks[:3]):
    first_line = c["text"].split("\n")[0][:80]
    print(f"  chunk{i}: pos={c['position']} | 首行: {first_line}")
