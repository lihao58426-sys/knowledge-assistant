"""验证 Redis 缓存——同问题两次提问，第二次命中缓存"""
import os
import time

# 确保连本地 Docker 的 Redis
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")

from redis_cache import _get_client, get_cached_answer, cache_answer

# 1. 确认 Redis 连通
client = _get_client()
if client is None:
    print("❌ Redis 连不上——确认 docker run redis-test 在运行")
    exit(1)
print("1. Redis 已连接\n")

# 2. 第一次——缓存没命中
q = "Python 装饰器是什么"
cached = get_cached_answer(q)
print(f"2. 第一次查 '{q}'")
print(f"   缓存命中: {cached is not None}")
assert cached is None, "第一次应该没缓存"

# 3. 存入缓存
cache_answer(q, "装饰器是一个函数——它接收一个函数，返回一个新函数，中间加上额外的逻辑。", ttl=60)
print("   已存入缓存 (TTL=60s)\n")

# 4. 第二次——应该命中
time.sleep(0.5)
cached = get_cached_answer(q)
print(f"3. 第二次查 '{q}'")
print(f"   缓存命中: {cached is not None}")
assert cached is not None, "第二次应该命中缓存"
print(f"   缓存内容: {cached[:50]}...\n")

# 5. 不同问题——不应该命中
q2 = "什么是 FastAPI"
cached2 = get_cached_answer(q2)
print(f"4. 查不同问题 '{q2}'")
print(f"   缓存命中: {cached2 is not None}")
assert cached2 is None, "不同问题不应该命中\n"

print("✅ 全部通过——Redis 缓存层工作正常")
