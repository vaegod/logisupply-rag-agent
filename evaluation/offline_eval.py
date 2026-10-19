from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from order_api.main import find_order
from order_api.knowledge import BM25Index, load_documents, tokenize


DOCS_DIR = ROOT_DIR / "docs"
TEST_FILE = Path(__file__).parent / "test_questions.csv"
RETRIEVAL_FILE = Path(__file__).parent / "retrieval_cases.csv"
RESULTS_DIR = Path(__file__).parent / "results"

ORDER_ID_PATTERN = re.compile(r"JD\d{7}", re.IGNORECASE)
EXCEPTION_ACTION_TERMS = (
    "怎么处理",
    "如何处理",
    "怎么办",
    "处理建议",
    "要不要升级",
    "人工升级",
    "怎么沟通",
    "客服怎么回复",
    "要不要赔付",
    "该做什么",
    "第一步做什么",
    "处理步骤",
    "连续投诉",
)


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def extract_order_id(question: str) -> str | None:
    match = ORDER_ID_PATTERN.search(question)
    return match.group(0).upper() if match else None


def classify_intent(question: str) -> str:
    order_id = extract_order_id(question)
    if order_id and any(term in question for term in EXCEPTION_ACTION_TERMS):
        return "exception"
    if "订单不存在" in question:
        return "exception"
    if order_id:
        return "order"
    return "knowledge"


def percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def evaluate_retrieval(index: BM25Index) -> tuple[dict[str, float | int], list[dict[str, str | float]]]:
    cases = load_csv(RETRIEVAL_FILE)
    details: list[dict[str, str | float]] = []
    reciprocal_ranks: list[float] = []
    recall_at_1 = 0
    recall_at_3 = 0
    latencies_ms: list[float] = []

    for case in cases:
        expected_docs = set(case["expected_docs"].split("|"))
        started = time.perf_counter()
        ranking = index.search(case["question"])
        latencies_ms.append((time.perf_counter() - started) * 1000)
        ranked_names = [name for name, _ in ranking]
        first_relevant_rank = next(
            (rank for rank, name in enumerate(ranked_names, start=1) if name in expected_docs),
            0,
        )
        reciprocal_rank = 1 / first_relevant_rank if first_relevant_rank else 0.0
        reciprocal_ranks.append(reciprocal_rank)
        recall_at_1 += int(bool(expected_docs.intersection(ranked_names[:1])))
        recall_at_3 += int(bool(expected_docs.intersection(ranked_names[:3])))

        details.append(
            {
                "id": case["id"],
                "question": case["question"],
                "expected_docs": case["expected_docs"],
                "top_1": ranked_names[0],
                "top_1_score": round(ranking[0][1], 4),
                "top_3": " | ".join(ranked_names[:3]),
                "first_relevant_rank": first_relevant_rank,
                "passed_at_3": "yes" if expected_docs.intersection(ranked_names[:3]) else "no",
            }
        )

    total = len(cases)
    metrics: dict[str, float | int] = {
        "case_count": total,
        "recall_at_1": round(recall_at_1 / total, 4) if total else 0.0,
        "recall_at_3": round(recall_at_3 / total, 4) if total else 0.0,
        "mrr": round(statistics.fmean(reciprocal_ranks), 4) if total else 0.0,
        "average_latency_ms": round(statistics.fmean(latencies_ms), 4) if total else 0.0,
        "p95_latency_ms": round(percentile_95(latencies_ms), 4),
    }
    return metrics, details


def evaluate_routing_and_tools() -> tuple[dict[str, float | int], list[dict[str, str]]]:
    cases = load_csv(TEST_FILE)
    details: list[dict[str, str]] = []
    route_correct = 0
    explicit_order_cases = 0
    extracted_order_ids = 0
    tool_lookup_success = 0

    for case in cases:
        predicted_type = classify_intent(case["question"])
        route_correct += int(predicted_type == case["type"])
        order_id = extract_order_id(case["question"])
        if order_id:
            explicit_order_cases += 1
            extracted_order_ids += 1
            if find_order(order_id) is not None:
                tool_lookup_success += 1

        details.append(
            {
                "id": case["id"],
                "question": case["question"],
                "expected_type": case["type"],
                "predicted_type": predicted_type,
                "route_correct": "yes" if predicted_type == case["type"] else "no",
                "order_id": order_id or "",
            }
        )

    total = len(cases)
    metrics: dict[str, float | int] = {
        "case_count": total,
        "intent_accuracy": round(route_correct / total, 4) if total else 0.0,
        "explicit_order_case_count": explicit_order_cases,
        "order_id_extraction_rate": (
            round(extracted_order_ids / explicit_order_cases, 4)
            if explicit_order_cases
            else 0.0
        ),
        "known_order_tool_success_rate": (
            round(tool_lookup_success / explicit_order_cases, 4)
            if explicit_order_cases
            else 0.0
        ),
    }
    return metrics, details


def build_report() -> tuple[dict, list[dict], list[dict]]:
    documents = load_documents()
    index = BM25Index(documents)
    retrieval_metrics, retrieval_details = evaluate_retrieval(index)
    routing_metrics, routing_details = evaluate_routing_and_tools()
    report = {
        "scope": "offline deterministic baseline; not Dify end-to-end quality",
        "document_count": len(documents),
        "retrieval": retrieval_metrics,
        "routing_and_tools": routing_metrics,
        "limitations": [
            "BM25 runs at document level and does not reproduce Dify chunking or vector retrieval.",
            "Intent routing is a transparent rule baseline, not Dify Question Classifier output.",
            "Tool success verifies local synthetic order lookup only; it does not cover a public deployment.",
            "Generated answer quality still requires a published Dify Chatflow and DIFY_API_KEY.",
        ],
    }
    return report, retrieval_details, routing_details


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_failure_cases(retrieval_details: list[dict], routing_details: list[dict]) -> None:
    retrieval_failures = [row for row in retrieval_details if row["passed_at_3"] == "no"]
    retrieval_top1_misses = [
        row for row in retrieval_details if str(row["first_relevant_rank"]) != "1"
    ]
    routing_failures = [row for row in routing_details if row["route_correct"] == "no"]
    lines = [
        "# 离线评测失败案例",
        "",
        "> 本文件只记录本地 BM25 与规则路由基线的失败，不代表 Dify 端到端回答质量。",
        "",
        f"- BM25 Recall@3 失败：{len(retrieval_failures)} 条",
        f"- BM25 Top 1 未命中但 Top 3 召回：{len(retrieval_top1_misses)} 条",
        f"- 规则路由失败：{len(routing_failures)} 条",
        "",
        "## BM25 Recall@3 失败",
        "",
    ]
    if retrieval_failures:
        for row in retrieval_failures:
            lines.extend(
                [
                    f"### Case {row['id']}：{row['question']}",
                    "",
                    f"- 期望文档：`{row['expected_docs']}`",
                    f"- Top 3：`{row['top_3']}`",
                    "- 建议：检查文档标题和业务同义词，或改用分块检索与向量/混合召回。",
                    "",
                ]
            )
    else:
        lines.extend(["当前固定测试集没有 Recall@3 失败。", ""])

    lines.extend(["## BM25 Top 1 弱案例", ""])
    if retrieval_top1_misses:
        for row in retrieval_top1_misses:
            lines.extend(
                [
                    f"### Case {row['id']}：{row['question']}",
                    "",
                    f"- 期望文档：`{row['expected_docs']}`",
                    f"- Top 1：`{row['top_1']}`",
                    f"- 首个相关文档排名：`{row['first_relevant_rank']}`",
                    f"- Top 3：`{row['top_3']}`",
                    "- 建议：分析通用词干扰，并在 Dify 端对比混合检索与重排结果。",
                    "",
                ]
            )
    else:
        lines.extend(["当前固定测试集没有 Top 1 弱案例。", ""])

    lines.extend(["## 规则路由失败", ""])
    if routing_failures:
        for row in routing_failures:
            lines.extend(
                [
                    f"- Case {row['id']}：{row['question']}（期望 `{row['expected_type']}`，预测 `{row['predicted_type']}`）"
                ]
            )
    else:
        lines.extend(
            [
                "当前固定测试集没有规则路由失败。该结果不能外推到真实用户问题，后续仍需补充口语、省略订单号和多意图样本。",
                "",
            ]
        )

    (RESULTS_DIR / "failure_cases.md").write_text("\n".join(lines), encoding="utf-8")


def write_results(report: dict, retrieval_details: list[dict], routing_details: list[dict]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "offline_metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_csv(RESULTS_DIR / "retrieval_cases.csv", retrieval_details)
    write_csv(RESULTS_DIR / "routing_cases.csv", routing_details)
    write_failure_cases(retrieval_details, routing_details)


def check_thresholds(report: dict) -> None:
    retrieval = report["retrieval"]
    routing = report["routing_and_tools"]
    checks = {
        "retrieval recall@3 >= 0.80": retrieval["recall_at_3"] >= 0.80,
        "intent accuracy >= 0.90": routing["intent_accuracy"] >= 0.90,
        "order id extraction == 1.00": routing["order_id_extraction_rate"] == 1.0,
        "known order tool success == 1.00": routing["known_order_tool_success_rate"] == 1.0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise SystemExit("Offline evaluation check failed: " + "; ".join(failures))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run reproducible local retrieval and routing evaluation.")
    parser.add_argument("--write", action="store_true", help="Write JSON/CSV/Markdown results.")
    parser.add_argument("--check", action="store_true", help="Fail if baseline thresholds are not met.")
    args = parser.parse_args()

    report, retrieval_details, routing_details = build_report()
    if args.write:
        write_results(report, retrieval_details, routing_details)
    if args.check:
        check_thresholds(report)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
