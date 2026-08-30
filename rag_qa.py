# -*- coding: utf-8 -*-
"""RAG 实测问答采集：问 5 个问题，UTF-8 写出，含来源"""
import json, urllib.request

URL = "http://rongno2.cn:8002/api/v1/chat"
QS = [
    "RAG 的流程是什么？",
    "ChromaDB 怎么建索引？",
    "pytest 怎么用临时目录？",
    "RFM 8 类客户怎么分类？",
    "Agent 循环怎么工作？",
]

out = open("rag_qa_out.txt", "w", encoding="utf-8")
for q in QS:
    try:
        req = urllib.request.Request(
            URL,
            data=json.dumps({"question": q}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        resp = json.load(urllib.request.urlopen(req, timeout=180))
        ans = resp.get("data", {}).get("answer", "") if resp.get("data") else ""
        out.write(f"Q: {q}\nA: {ans}\n{'='*60}\n\n")
    except Exception as e:
        out.write(f"Q: {q}\nERR: {e}\n{'='*60}\n\n")
out.close()
print("done, written to rag_qa_out.txt (utf-8)")
