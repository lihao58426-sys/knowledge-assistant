"""
Redis 缓存层
============
为 RAG 问答提供查询缓存和会话管理。Redis 不可用时自动降级——不报错、不阻塞。
"""

import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)

# ── 连接 Redis ──
_redis_client = None


import time as _time

# 全局状态：避免每次请求都重试连 Redis
_redis_client = None
_redis_unavailable_until = 0.0  # 时间戳——在此之前不重试


def _get_client():
    """懒加载 Redis 连接——连不上 60 秒内不再重试"""
    global _redis_client, _redis_unavailable_until

    now = _time.time()
    if now < _redis_unavailable_until:
        return None  # 刚才连不上，跳过

    if _redis_client is not None:
        try:
            _redis_client.ping()
            return _redis_client
        except Exception:
            _redis_client = None

    try:
        import redis
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        db = int(os.getenv("REDIS_DB", "0"))
        password = os.getenv("REDIS_PASSWORD", None)

        _redis_client = redis.Redis(
            host=host, port=port, db=db, password=password,
            socket_connect_timeout=0.5, socket_timeout=0.5,
        )
        _redis_client.ping()
        _redis_unavailable_until = 0.0  # 连上了，重置标记
        logger.info(f"Redis 已连接: {host}:{port}")
        return _redis_client
    except Exception:
        logger.info("Redis 未连接——60s 内不再重试")
        _redis_unavailable_until = now + 60  # 60 秒内不走连接逻辑
        return None


# ── 查询缓存 ──

def _cache_key(question: str) -> str:
    """把问题转成一个安全的 Redis key

    "FastAPI 怎么部署？" → "ka:query:fad390e2e5..."
    同一个问题生成同样的 key——达到"同样的问题命中缓存"的效果。
    """
    normalized = question.strip().lower()
    hashed = hashlib.md5(normalized.encode()).hexdigest()
    return f"ka:query:{hashed}"


def get_cached_answer(question: str) -> str | None:
    """查缓存——返回缓存的答案，没有就返回 None"""
    client = _get_client()
    if client is None:
        return None

    key = _cache_key(question)
    try:
        data = client.get(key)
        if data:
            logger.info(f"缓存命中: {question[:50]}...")
            return data.decode("utf-8")
    except Exception as e:
        logger.warning(f"Redis 查询失败: {e}")

    return None


def cache_answer(question: str, answer: str, ttl: int = 1800) -> None:
    """缓存答案——默认 30 分钟过期"""
    client = _get_client()
    if client is None:
        return

    key = _cache_key(question)
    try:
        client.setex(key, ttl, answer.encode("utf-8"))
        logger.info(f"已缓存: {question[:50]}... (TTL={ttl}s)")
    except Exception as e:
        logger.warning(f"Redis 写入失败: {e}")


# ── 会话管理 ──

def get_session(session_id: str) -> list | None:
    """从 Redis 获取会话历史"""
    client = _get_client()
    if client is None:
        return None

    key = f"ka:session:{session_id}"
    try:
        data = client.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Redis 读取会话失败: {e}")

    return None


def save_session(session_id: str, history: list, ttl: int = 3600) -> None:
    """保存会话历史到 Redis——默认 1 小时过期"""
    client = _get_client()
    if client is None:
        return

    key = f"ka:session:{session_id}"
    try:
        client.setex(key, ttl, json.dumps(history, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"Redis 保存会话失败: {e}")
