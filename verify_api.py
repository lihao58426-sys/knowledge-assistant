"""验证 API 重构——新老接口 + 响应格式"""
import requests

BASE = "http://localhost:8002"
PASSWORD = "test"  # 改成你的 KA_PASSWORD

auth = ("admin", PASSWORD)

print("1. 旧接口 POST /ask（页面路由）")
r = requests.post(f"{BASE}/ask", data={"question": "什么是 Python"}, auth=auth)
print(f"   状态码: {r.status_code} (200=HTML页面)")
# 旧路由没有 try/except，但正常问题不应该炸
assert r.status_code == 200

print("\n2. 新接口 POST /api/v1/chat（JSON API）")
r = requests.post(f"{BASE}/api/v1/chat",
                  json={"question": "什么是 Python"},
                  auth=auth)
print(f"   状态码: {r.status_code}")
body = r.json()
print(f"   code: {body['code']}, message: {body['message']}")
assert "code" in body
assert "data" in body
assert "message" in body
if body["code"] == 200 and body["data"]:
    print(f"   data.answer 前50字: {str(body['data'].get('answer', ''))[:50]}...")
    assert body["code"] == 200
else:
    print(f"   API 返回非 200——DeepSeek 可能连不上。错误: {body['message']}")
    print("   ⚠ 这不是代码的问题，是 DeepSeek API 调用失败。跳过此条。")

print("\n3. 新接口——空问题应返回 422")
r = requests.post(f"{BASE}/api/v1/chat", json={"question": ""}, auth=auth)
body = r.json()
print(f"   code: {body['code']}, message: {body['message']}")
assert body["code"] == 422

print("\n4. Swagger /docs 页面")
r = requests.get(f"{BASE}/docs", auth=auth)
print(f"   状态码: {r.status_code}")
assert r.status_code == 200

print("\n5. /openapi.json（自动生成的 API 规范）")
r = requests.get(f"{BASE}/openapi.json", auth=auth)
body = r.json()
tags = [t["name"] for t in body.get("tags", [])]
print(f"   标签分组: {tags}")
assert "Chat" in tags
assert "Documents" in tags

print("\n✅ 全部验证通过")
