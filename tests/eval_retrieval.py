"""
RAG 检索评估脚本 — MRR + Recall@K
==================================
用法：python tests/eval_retrieval.py
输出：每题得分 + 汇总统计
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_engine import query


def load_questions(path: str = "tests/eval_questions.json") -> list[dict]:
    """加载测试问题集"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, path), "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate(questions: list[dict], model_key: str = "v2", top_k: int = 5) -> dict:
    """跑评估——对每道题用检索取 TOP-K，计算 MRR 和 Recall@K"""
    results = []
    total_mrr = 0.0
    total_recall = 0.0

    for q in questions:
        hits = query(q["question"], model_key=model_key, top_k=top_k)
        retrieved_sources = [h[1].get("source", "") for h in hits]

        expect = set(q["expect_files"])
        found = set()
        mrr = 0.0

        # 计算 MRR：第一个命中的排名
        for rank, src in enumerate(retrieved_sources, 1):
            for exp_file in expect:
                if exp_file in src:
                    found.add(exp_file)
                    if mrr == 0.0:
                        mrr = 1.0 / rank
                    break

        # 计算 Recall@K
        recall = len(found & expect) / len(expect) if expect else 0.0

        total_mrr += mrr
        total_recall += recall

        results.append({
            "id": q["id"],
            "question": q["question"],
            "MRR": round(mrr, 3),
            "Recall@5": round(recall, 3),
            "found": list(found),
            "expect": list(expect),
        })

    n = len(questions)
    return {
        "questions": results,
        "avg_MRR": round(total_mrr / n, 3),
        "avg_Recall@5": round(total_recall / n, 3),
        "total_questions": n,
        "model": model_key,
        "top_k": top_k,
    }


if __name__ == "__main__":
    print("加载测试问题...")
    qs = load_questions()
    print(f"共 {len(qs)} 题\n")

    report = evaluate(qs)

    for r in report["questions"]:
        icon = "✅" if r["MRR"] > 0 else "❌"
        print(f"{icon} Q{r['id']}: {r['question'][:40]}...")
        print(f"   MRR={r['MRR']:.2f}  Recall@5={r['Recall@5']:.2f}")
        print(f"   命中: {r['found']}")

    print(f"\n{'='*50}")
    print(f"平均 MRR: {report['avg_MRR']}")
    print(f"平均 Recall@5: {report['avg_Recall@5']}")
    print(f"共 {report['total_questions']} 题 | 模型: {report['model']} | Top-K: {report['top_k']}")
