"""
RAG 问答引擎（多模型支持）
=========================
用法：
  python rag_engine.py "问题"             默认中文模型
  python rag_engine.py --v1 "问题"        英文模型
"""

import os

# ── 离线模型加载 ──
# sentence-transformers 默认每次加载模型都会联网到 huggingface.co 检查更新。
# 国内网络连不上，会导致每次问答卡住数分钟（连接超时后重试 5 次）。
# 模型已缓存在本地，这里强制离线，直接读缓存。
# 上云若需联网下载模型，可在启动前设 HF_HUB_OFFLINE=0 覆盖此默认值。
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import sys
import chromadb
from sentence_transformers import SentenceTransformer
from chromadb.api.types import EmbeddingFunction, Embeddings
import requests

from redis_cache import get_cached_answer, cache_answer

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_CHAT_URL = "https://api.deepseek.com/v1/chat/completions"
TOP_K = 5

# ── 模型注册表（跟 index.py 保持一致）──
MODELS = {
    "v1": {
        "source": "sentence-transformers/all-MiniLM-L6-v2",
        "chroma_dir": "./chroma_db",
        "collection": "knowledge_base_v1",
    },
    "v2": {
        "source": "shibing624/text2vec-base-chinese",
        "chroma_dir": "./chroma_db",
        "collection": "knowledge_base_v2",
    },
}


class ModelEmbedding(EmbeddingFunction):
    def __init__(self, model_source: str):
        self.model = SentenceTransformer(model_source)

    def __call__(self, texts: list[str]) -> Embeddings:
        return self.model.encode(texts).tolist()


# ── 模型单例缓存 ──
# 启动时加载一次，后面所有问答复用。每问从 ~8 秒降到 ~2 秒。
_embedding_cache: dict[str, ModelEmbedding] = {}
_client_cache: dict[str, chromadb.PersistentClient] = {}


def _get_embedding(model_key: str) -> ModelEmbedding:
    """取缓存的 embedding 模型，没有就加载一个"""
    if model_key not in _embedding_cache:
        cfg = MODELS[model_key]
        _embedding_cache[model_key] = ModelEmbedding(cfg["source"])
    return _embedding_cache[model_key]


def _get_client(model_key: str) -> chromadb.PersistentClient:
    """取缓存的 ChromaDB 客户端"""
    if model_key not in _client_cache:
        cfg = MODELS[model_key]
        _client_cache[model_key] = chromadb.PersistentClient(path=cfg["chroma_dir"])
    return _client_cache[model_key]


def query(question: str, model_key: str = "v2", top_k: int = TOP_K) -> list:
    cfg = MODELS[model_key]
    client = _get_client(model_key)
    embed_fn = _get_embedding(model_key)
    collection = client.get_collection(cfg["collection"], embedding_function=embed_fn)

    results = collection.query(query_texts=[question], n_results=top_k)
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    return list(zip(docs, metas))


# ── V3: 对话记忆 ──
MAX_HISTORY = 5  # 每个会话保留最近 5 轮
_sessions: dict[str, list] = {}  # session_id → [{role, content}, ...]


def get_session(session_id: str = "default") -> list:
    """获取或创建会话历史"""
    if session_id not in _sessions:
        _sessions[session_id] = []
    return _sessions[session_id]


def ask(question: str, model_key: str = "v2", session_id: str = "default", project_filter: str = "") -> str:
    # ── Redis 缓存检查 ──
    cached = get_cached_answer(question)
    if cached:
        return f"{cached}\n\n*(来自缓存)*"

    # 检索
    results = query(question, model_key)

    # 严格项目过滤：选定项目后，只允许该项目的文件
    if project_filter:
        pf = project_filter.replace('-', '').lower()
        filtered = [(doc, meta) for doc, meta in results
                    if pf in meta.get("source", "").replace('-', '').lower()]
        if filtered:
            results = filtered
        else:
            # 项目内没搜到 → 明确告知，不越界
            return (f"在「{project_filter}」项目中未找到相关内容。\n"
                    f"建议：切换到「全部项目」再问，或者换个更具体的问法。")

    if not results:
        return "知识库中没有找到相关内容。"

    context_parts = []
    for i, (doc, meta) in enumerate(results, 1):
        source = meta.get("source", "未知文件")
        context_parts.append(f"[片段{i}] 来源: {source}\n{doc}")

    context = "\n\n".join(context_parts)

    # 构建消息列表：系统指令 + 历史对话 + 当前问题
    messages = [{
        "role": "system",
        "content": "你是一个技术导师，擅长用用户自己的项目代码作为案例来讲解概念。回答基于提供的资料，不编造。遇到概念问题时要展开：是什么→为什么→在项目的哪里→怎么实现的。"
    }]

    # 加入对话历史
    session = get_session(session_id)
    for turn in session[-MAX_HISTORY * 2:]:  # 最近 N 轮（一问一答 = 2 条）
        messages.append(turn)

    # 当前问题（带知识库上下文）
    prompt = f"""你是一个技术导师。用户正在学习自己的项目代码，请用他自己的项目作为案例来讲解。

要求：
1. 用资料中的实际代码和文件名作为例子，不要用教科书里的通用例子
2. 如果用户问的是概念或"怎么实现"，展开讲解：是什么→为什么→在项目的哪里→怎么实现的
3. 引用具体的文件名和行号位置
4. 如果资料中没有答案，诚实说"资料中没有相关信息"，不要编造

资料：
{context}

用户问题：{question}

请回答："""
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 1200,
    }

    resp = requests.post(DEEPSEEK_CHAT_URL, headers=headers, json=data, timeout=60)
    resp.raise_for_status()
    answer = resp.json()["choices"][0]["message"]["content"].strip()

    # 存入历史
    session.append({"role": "user", "content": question})
    session.append({"role": "assistant", "content": answer})
    if len(session) > MAX_HISTORY * 2:
        session.pop(0)
        session.pop(0)

    # 去重来源
    seen = set()
    unique_sources = []
    for _, meta in results:
        src = meta.get('source', '未知')
        if src not in seen:
            seen.add(src)
            unique_sources.append(src)
    sources = "\n".join(f"  - {s}" for s in unique_sources)
    final_answer = f"{answer}\n\n参考来源：\n{sources}"

    # ── 存入 Redis 缓存 ──
    cache_answer(question, final_answer)

    return final_answer


if __name__ == "__main__":
    if "--v1" in sys.argv:
        model = "v1"
        sys.argv.remove("--v1")
    else:
        model = "v2"

    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
    else:
        q = input("请输入问题: ")

    print("\n思考中...\n")
    print(ask(q, model_key=model))
