"""
RAG 评估汇总报告生成器
====================
用法：python tests/eval_report.py  →  打印报告 Markdown，并生成 .md 文件
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_retrieval import evaluate as eval_retrieval, load_questions
from eval_llm_judge import evaluate_with_judge


def generate_report() -> str:
    qs = load_questions()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # R2 — 检索
    report_r2 = eval_retrieval(qs, top_k=5)

    # R3 — LLM 打分（跑 5 题）
    report_r3 = evaluate_with_judge(qs, top_n=5)

    lines = [
        "# RAG 检索质量评估报告",
        f"日期：{now}",
        f"模型：{report_r2['model']} | Top-K：{report_r2['top_k']} | 评估题数：{report_r2['total_questions']}",
        "",
        "---",
        "",
        "## 一、综合评分",
        "",
    ]

    lines.append(f"- **平均 MRR：{report_r2['avg_MRR']}**（排第 1 得分 1，排第 K 得分 1/K）")
    lines.append(f"- **平均 Recall@5：{report_r2['avg_Recall@5']}**（预期相关文档中被搜到的比例）")
    lines.append("")
    lines.append(f"- **LLM-Judge 平均准确性：{report_r3['avg_accuracy']}/5")
    lines.append(f"- **LLM-Judge 平均完整性：{report_r3['avg_completeness']}/5")
    lines.append(f"- **LLM-Judge 平均有用性：{report_r3['avg_usefulness']}/5")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 二、检索维度 · 逐题明细")
    lines.append("")
    lines.append("| # | 问题 | MRR | Recall@5 | 命中文件 |")
    lines.append("|:--:|------|:--:|:--:|------|")
    for r in report_r2["questions"]:
        found_str = ", ".join(r["found"][:2]) or "无命中"
        lines.append(f"| {r['id']} | {r['question'][:30]}... | {r['MRR']:.2f} | {r['Recall@5']:.2f} | {found_str} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 三、LLM-Judge 维度 · 生成质量")
    lines.append("")
    lines.append("| # | 问题 | 准确性 | 完整性 | 有用性 | 回答摘要 |")
    lines.append("|:--:|------|:--:|:--:|:--:|------|")
    for r in report_r3["results"]:
        lines.append(f"| {r['id']} | {r['question'][:25]}... | {r['scores'].get('accuracy',0)} | {r['scores'].get('completeness',0)} | {r['scores'].get('usefulness',0)} | {r['answer_preview'][:60]}... |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 四、解读")
    lines.append("")
    mrr = report_r2["avg_MRR"]
    recall = report_r2["avg_Recall@5"]
    acc = report_r3["avg_accuracy"]

    if mrr < 0.3:
        lines.append("- **检索需要优化。** MRR < 0.3 意味着多数问题的正确答案没有排在检索结果前列。建议：①检查知识库索引是否包含了所有项目的最新版本 ②对比不同 CHUNK_SIZE（试试 600 和 400）。")
    else:
        lines.append("- **检索表现中等偏上。** MRR > 0.3 说明多数问题正确答案能进入 Top-5。")

    if acc > 3.5:
        lines.append("- **生成质量稳定。** LLM-Judge 平均分 > 3.5/5，说明即使检索不够完美，DeepSeek 仍能从检索结果中提取有效信息并组织成有用的回答。")
    lines.append("- **团队建议**：每次修改索引参数或模型后可重新运行本报告进行对比（A/B test）。")

    report_md = "\n".join(lines)
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 带时间戳的存档（用于 A/B 对比，不覆盖旧报告）
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path_latest = os.path.join(base, "RAG评估报告-最新.md")
    path_archive = os.path.join(base, f"RAG评估报告-{stamp}.md")
    for p in [path_latest, path_archive]:
        with open(p, "w", encoding="utf-8") as f:
            f.write(report_md)
    return report_md


if __name__ == "__main__":
    report = generate_report()
    print(report)
