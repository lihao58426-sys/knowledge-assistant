"""
RAG 问答 — LangChain LCEL 版本
===============================
跟 rag_engine.py 做同一件事——检索 ChromaDB → 拼上下文 → 调 DeepSeek → 返回答案。
区别：用 LangChain 的 LCEL 管道串联，不手写 if/else 和 requests 调用。

手写版 vs LangChain 版对比：
  手写：~40 行，自己管检索→拼 prompt→调 API→取结果
  LCEL：~15 行，用 | 管道串联，换模型/改 prompt 更快

用法：
  python rag_langchain.py "装饰器是什么"
"""

import os
import sys

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_openai import ChatOpenAI

# ── 导入现有的检索函数（不动 rag_engine.py）──
from rag_engine import query, TOP_K

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ── 1. 把 ChromaDB 检索包装成 LangChain 可用的函数 ──

def _retrieve(question: str) -> str:
    """检索 ChromaDB → 拼成一段上下文字符串

    LCEL 不认识 ChromaDB——它只认识"输入→输出"的函数。
    这里把 query() 的结果格式化成一段文本，喂给 prompt。
    """
    results = query(question, top_k=TOP_K)
    if not results:
        return "知识库中没有找到相关内容。"

    parts = []
    for i, (doc, meta) in enumerate(results, 1):
        source = meta.get("source", "未知文件")
        parts.append(f"[片段{i}] 来源: {source}\n{doc}")

    return "\n\n".join(parts)


# ── 2. LLM —— 指向 DeepSeek ──

_llm = ChatOpenAI(
    model="deepseek-v4-pro",
    base_url="https://api.deepseek.com/v1",
    api_key=DEEPSEEK_API_KEY,
    temperature=0.3,
    max_tokens=1200,
)


# ── 3. Prompt 模板 ──

_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个技术导师，擅长用用户自己的项目代码作为案例来讲解概念。"
               "回答基于下面提供的资料，不编造。"
               "遇到概念问题时要展开：是什么→为什么→在项目的哪里→怎么实现的。"
               "\n\n参考资料：\n{context}"),
    ("human", "{question}"),
])


# ── 4. LCEL 管道 —— 用 | 串联 ──

chain = (
    {
        "context": RunnableLambda(_retrieve),    # ① 检索
        "question": RunnablePassthrough(),        # ② 用户问题原样传给 prompt
    }
    | _prompt                                      # ③ 填 prompt 模板
    | _llm                                         # ④ 调 LLM
    | StrOutputParser()                            # ⑤ 把 LLM 输出转成纯文本
)


# ── 5. 调用入口（跟手写版 ask() 一样的接口）──

def ask_langchain(question: str) -> str:
    """用 LangChain LCEL 管道做 RAG 问答"""
    return chain.invoke(question)


# ── CLI ──

if __name__ == "__main__":
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
    else:
        q = input("请输入问题: ")

    print("\n思考中...\n")
    answer = ask_langchain(q)
    print(answer)
