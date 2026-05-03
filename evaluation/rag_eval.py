from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from urllib import error, request

DIFY_API_BASE = os.getenv("DIFY_API_BASE", "https://api.dify.ai/v1")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")

BASE_DIR = Path(__file__).parent
INPUT_FILE = BASE_DIR / "test_questions.csv"
OUTPUT_FILE = BASE_DIR / "eval_result.csv"


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
        },
        method="POST",
    )

    with request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data.get("answer", "")


def keyword_hit(answer: str, expected_keyword: str) -> float:
    keywords = [keyword.strip() for keyword in expected_keyword.split() if keyword.strip()]
    if not keywords:
        return 0.0

    hit_count = sum(1 for keyword in keywords if keyword in answer)
    return hit_count / len(keywords)


def main() -> None:
    results: list[dict[str, str | float]] = []

    with INPUT_FILE.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            question = row["question"]
            expected_keyword = row["expected_keyword"]

            print(f"正在评测：{question}")

            try:
                answer = ask_dify(question)
                score = keyword_hit(answer, expected_keyword)
                passed = "是" if score >= 0.5 else "否"
            except (RuntimeError, error.URLError, TimeoutError, ValueError) as exc:
                answer = f"ERROR: {exc}"
                score = 0.0
                passed = "否"

            results.append(
                {
                    "id": row["id"],
                    "question": question,
                    "type": row["type"],
                    "expected_keyword": expected_keyword,
                    "answer": answer.replace("\n", " "),
                    "keyword_score": round(score, 2),
                    "passed": passed,
                }
            )

            time.sleep(1)

    with OUTPUT_FILE.open("w", encoding="utf-8", newline="") as file:
        fieldnames = [
            "id",
            "question",
            "type",
            "expected_keyword",
            "answer",
            "keyword_score",
            "passed",
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    passed_count = sum(1 for result in results if result["passed"] == "是")
    total = len(results)
    ratio = passed_count / total if total else 0.0
    print(f"评测完成：{passed_count}/{total} 通过，通过率 {ratio:.2%}")


if __name__ == "__main__":
    main()

