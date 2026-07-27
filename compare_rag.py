"""手写版 vs LangChain 版质量对比"""
import time
from rag_engine import ask
from rag_langchain import ask_langchain

questions = [
    "装饰器是什么",
    "FastAPI 怎么部署",
    "ChromaDB 和传统数据库有什么区别",
]

for i, q in enumerate(questions, 1):
    print(f"\n{'='*60}")
    print(f"问题 {i}: {q}")
    print(f"{'='*60}")

    # 手写版
    t0 = time.time()
    a1 = ask(q)
    t1 = time.time() - t0
    print(f"\n📝 手写版 ({t1:.1f}s):")
    print(a1[:300])

    # LangChain 版
    t0 = time.time()
    a2 = ask_langchain(q)
    t2 = time.time() - t0
    print(f"\n🤖 LangChain版 ({t2:.1f}s):")
    print(a2[:300])

print(f"\n{'='*60}")
print("✅ 对比完成——重点看：回答是否基于项目代码、是否编造、逻辑是否通顺")
