from __future__ import annotations

import csv
import json
import os
import statistics
import time
from pathlib import Path
from urllib import error, request

DIFY_API_BASE = os.getenv("DIFY_API_BASE", "https://api.dify.ai/v1")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")
USER_AGENT = "LogiSupply-RAG-Agent-Eval/1.0"

BASE_DIR = Path(__file__).parent
INPUT_FILE = BASE_DIR / "test_questions.csv"
OUTPUT_FILE = BASE_DIR / "eval_result.csv"
SUMMARY_FILE = BASE_DIR / "eval_summary.json"


def ask_dify(question: str) -> str:
    if not DIFY_API_KEY:
        raise RuntimeError("请先设置环境变量 DIFY_API_KEY")

    payload = json.dumps(
        {
            "inputs": {},
            "query": question,
            "response_mode": "blocking",
            "conversation_id": "",
            "user": "eval-user-001",
        }
    ).encode("utf-8")

    req = request.Request(
        url=f"{DIFY_API_BASE}/chat-messages",
        data=payload,
        headers={
            "Authorization": f"Bearer {DIFY_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(detail)
            message = payload.get("message") or payload.get("code") or detail
        except json.JSONDecodeError:
            message = detail or str(exc)

        if exc.code == 400 and "Workflow not published" in message:
            raise RuntimeError(
                "Dify 应用尚未发布。请先在 Dify Chatflow 中点击“发布”，再运行评测脚本。"
            ) from exc

        raise RuntimeError(f"Dify API 请求失败：HTTP {exc.code} - {message}") from exc

    return data.get("answer", "")


def keyword_hit(answer: str, expected_keyword: str) -> float:
    keywords = [keyword.strip() for keyword in expected_keyword.split() if keyword.strip()]
    if not keywords:
        return 0.0

    hit_count = sum(1 for keyword in keywords if keyword in answer)
    return hit_count / len(keywords)


def percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95 + 0.9999) - 1))
    return ordered[index]


def summarize_results(results: list[dict[str, str | float]]) -> dict:
    total = len(results)
    successful = [result for result in results if result["api_success"] == "是"]
    passed = [result for result in results if result["passed"] == "是"]
    latencies = [float(result["latency_ms"]) for result in successful]
    per_type: dict[str, dict[str, int | float]] = {}

    for question_type in sorted({str(result["type"]) for result in results}):
        typed = [result for result in results if result["type"] == question_type]
        typed_success = [result for result in typed if result["api_success"] == "是"]
        typed_passed = [result for result in typed if result["passed"] == "是"]
        per_type[question_type] = {
            "count": len(typed),
            "api_success_rate": round(len(typed_success) / len(typed), 4) if typed else 0.0,
            "keyword_pass_rate": round(len(typed_passed) / len(typed), 4) if typed else 0.0,
        }

    return {
        "scope": "published Dify Chatflow end-to-end evaluation",
        "case_count": total,
        "api_success_rate": round(len(successful) / total, 4) if total else 0.0,
        "keyword_pass_rate": round(len(passed) / total, 4) if total else 0.0,
        "average_latency_ms": round(statistics.fmean(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(percentile_95(latencies), 2),
        "per_type": per_type,
    }


def main() -> None:
    results: list[dict[str, str | float]] = []

    with INPUT_FILE.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            question = row["question"]
            expected_keyword = row["expected_keyword"]

            print(f"正在评测：{question}")

            started = time.perf_counter()
            try:
                answer = ask_dify(question)
                score = keyword_hit(answer, expected_keyword)
                passed = "是" if score >= 0.5 else "否"
                api_success = "是"
                error_message = ""
            except (RuntimeError, error.URLError, TimeoutError, ValueError) as exc:
                answer = ""
                score = 0.0
                passed = "否"
                api_success = "否"
                error_message = str(exc)

            latency_ms = round((time.perf_counter() - started) * 1000, 2)

            results.append(
                {
                    "id": row["id"],
                    "question": question,
                    "type": row["type"],
                    "expected_keyword": expected_keyword,
                    "answer": answer.replace("\n", " "),
                    "keyword_score": round(score, 2),
                    "passed": passed,
                    "api_success": api_success,
                    "latency_ms": latency_ms,
                    "error": error_message,
                }
            )

            time.sleep(float(os.getenv("DIFY_EVAL_DELAY_SECONDS", "1")))

    with OUTPUT_FILE.open("w", encoding="utf-8", newline="") as file:
        fieldnames = [
            "id",
            "question",
            "type",
            "expected_keyword",
            "answer",
            "keyword_score",
            "passed",
            "api_success",
            "latency_ms",
            "error",
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    summary = summarize_results(results)
    SUMMARY_FILE.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
