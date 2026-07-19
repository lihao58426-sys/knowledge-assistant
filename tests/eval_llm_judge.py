"""
LLM-as-Judge 评估脚本 — 让 DeepSeek 给 RAG 回答质量打分
======================================================
用法：python tests/eval_llm_judge.py
输出：每题三围评分（准确性/完整性/有用性，各 1-5 分）
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from rag_engine import ask

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"


def load_questions(path: str = "tests/eval_questions.json") -> list[dict]:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, path), "r", encoding="utf-8") as f:
        return json.load(f)


def judge_answer(question: str, answer: str) -> dict:
    """让 DeepSeek 打分：准确性、完整性、有用性各 1-5"""
    prompt = f"""你是一个严格的技术评审。给以下 AI 回答打分。

问题：{question}

AI 回答：
{answer}

请从三个维度打分（1=很差, 5=完美），只输出 JSON，不要解释：
{{"accuracy": <1-5>, "completeness": <1-5>, "usefulness": <1-5>}}"""

    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1, "max_tokens": 100,
    }
    resp = requests.post(DEEPSEEK_URL, headers=headers, json=data, timeout=60)
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()

    # 解析 JSON
    if raw.startswith("```"): raw = raw.split("\n", 1)[1].rsplit("\n```", 1)[0]
    return json.loads(raw)


def evaluate_with_judge(questions: list[dict], top_n: int = 30) -> dict:
    """逐题问 RAG → 拿回答 → 发给 Judge 打分"""
    results = []
    total = {"accuracy": 0.0, "completeness": 0.0, "usefulness": 0.0}

    for i, q in enumerate(questions[:top_n]):
        print(f"[{i+1}/{top_n}] 评估: {q['question'][:50]}...")

        answer = ask(q["question"])
        # ask() 返回的是完整答案含"参考来源"，取前半部分纯回答
        answer_clean = answer.split("参考来源")[0].strip()

        try:
            scores = judge_answer(q["question"], answer_clean)
        except Exception as e:
            print(f"  打分失败: {e}")
            scores = {"accuracy": 0, "completeness": 0, "usefulness": 0}

        total["accuracy"] += scores.get("accuracy", 0)
        total["completeness"] += scores.get("completeness", 0)
        total["usefulness"] += scores.get("usefulness", 0)

        results.append({
            "id": q["id"], "question": q["question"],
            "scores": scores,
            "answer_preview": answer_clean[:100],
        })
        print(f"  准确性:{scores.get('accuracy',0)} 完整性:{scores.get('completeness',0)} 有用性:{scores.get('usefulness',0)}")
        time.sleep(0.5)

    n = len(results) or 1
    return {
        "results": results,
        "avg_accuracy": round(total["accuracy"] / n, 2),
        "avg_completeness": round(total["completeness"] / n, 2),
        "avg_usefulness": round(total["usefulness"] / n, 2),
    }


if __name__ == "__main__":
    qs = load_questions()
    print(f"加载 {len(qs)} 题，评估前 5 题（省 API 费用）\n")
    report = evaluate_with_judge(qs, top_n=5)
    print(f"\n{'='*50}")
    print(f"平均准确性: {report['avg_accuracy']}")
    print(f"平均完整性: {report['avg_completeness']}")
    print(f"平均有用性: {report['avg_usefulness']}")
