"""Real Embedding/Milvus comparison. Metrics describe retrieval, not answer correctness."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from order_api.knowledge import BM25Index, load_documents
from order_api.rag import load_retriever


PARAPHRASES = [
    ("冷藏车制冷机坏了，车里的药品越来越热，客服该联系谁？", ["03_冷链运输规范.md"]),
    ("生鲜在路上失温了，可以凭经验继续送吗？", ["03_冷链运输规范.md"]),
    ("货物比约定时间晚了两天多，应该开哪种异常单？", ["04_订单延迟处理SOP.md"]),
    ("客户反复催货并投诉，包裹还在中转站，该如何升级？", ["04_订单延迟处理SOP.md", "07_客户投诉处理规则.md"]),
    ("箱子到了以后压瘪了，货物也坏了，要先留下什么证据？", ["05_货物破损处理SOP.md"]),
    ("仓库货架实物和电脑台账数量对不上，该怎么查？", ["09_库存盘点规范.md"]),
    ("东西轻但是箱子很占地方，运费按什么算？", ["08_运输费用计算规则.md"]),
    ("买家想把收到的货换一件，仓库接下来如何处理？", ["06_退换货处理规则.md"]),
    ("供应商把货送到仓门口之前需要做什么准备？", ["01_仓储入库流程.md"]),
    ("包裹从仓库发走以前，要核对哪些东西？", ["02_仓储出库流程.md"]),
]


def evaluate():
    load_dotenv(ROOT / ".env", override=False)
    engine = load_retriever()
    real_embedder = engine.embedder
    cache = {}
    calls = 0

    def cached(texts):
        nonlocal calls
        key = tuple(texts)
        if key not in cache:
            cache[key] = real_embedder(texts)
            calls += 1
        return cache[key]

    engine.embedder = cached
    try:
        if not engine.ready():
            raise RuntimeError("Run python -m order_api.rag_index before evaluation")
        with (ROOT / "evaluation/retrieval_cases.csv").open(encoding="utf-8-sig", newline="") as handle:
            cases = [{"question": row["question"], "expected": row["expected_docs"].split("|"), "group": "existing"}
                     for row in csv.DictReader(handle)]
        cases += [{"question": q, "expected": docs, "group": "paraphrase"} for q, docs in PARAPHRASES]
        baseline = BM25Index(load_documents())
        assert all(set(case["expected"]) <= set(baseline.documents) for case in cases), "Unknown expected source"
        details = []
        for case in cases:
            question = case["question"]
            original = [name for name, score in baseline.search(question) if score > 0][:3]
            lexical = [engine.by_id[key].source for key, score in engine.bm25.search(question) if score > 0][:3]
            dense = [engine.by_id[key].source for key, score in engine.dense(question)][:3]
            hybrid = engine.search(question)
            if hybrid["degraded"]:
                raise RuntimeError("Evaluation requires actual dense retrieval; no fallback accepted")
            details.append({**case, "document_bm25": original, "chunk_bm25": lexical,
                            "dense": dense, "hybrid": [r["source"] for r in hybrid["results"]],
                            "hybrid_citations": [r["citation"] for r in hybrid["results"]]})
        metrics = {}
        for group in ("all", "existing", "paraphrase"):
            rows = [r for r in details if group == "all" or r["group"] == group]
            metrics[group] = {"questions": len(rows)}
            for method in ("document_bm25", "chunk_bm25", "dense", "hybrid"):
                metrics[group][method] = {
                    "hit_at_1": round(sum(bool(set(r["expected"]) & set(r[method][:1])) for r in rows) / len(rows), 4),
                    "hit_at_3": round(sum(bool(set(r["expected"]) & set(r[method][:3])) for r in rows) / len(rows), 4),
                    "mean_required_document_recall_at_3": round(sum(
                        len(set(r["expected"]) & set(r[method][:3])) / len(set(r["expected"])) for r in rows) / len(rows), 4)}
        negatives = []
        for question in ("明天上海会下雨吗？", "请告诉我股票买哪一只", "zzzxxyy"):
            result = engine.search(question)
            negatives.append({"question": question, "no_evidence": result["no_evidence"],
                              "returned_sources": [r["source"] for r in result["results"]],
                              "note": "非知识库问题；返回片段不代表可回答，需另验生成层拒答"})
        report = {"created_at": datetime.now(timezone.utc).isoformat(), "index": engine.index_info("ready"),
                  "embedding_calls": calls, "embedding_kind": "real_api", "metrics": metrics,
                  "definitions": {"hit_at_k": "top-k片段来源至少命中一份预期文档；原document_bm25按文档计",
                                  "required_document_recall": "预期文档中被top-3来源覆盖的比例，多文档题不会只算命中一份",
                                  "limits": "35例固定开发集，10例新增改写；不是独立盲测、答案准确率或延迟基准；同次相同问题向量缓存复用"},
                  "details": details, "out_of_scope_probes": negatives}
        path = ROOT / "evaluation/results/hybrid_retrieval.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"report": str(path), "index": report["index"], "metrics": metrics,
                          "out_of_scope_probes": negatives}, ensure_ascii=False, indent=2))
    finally:
        engine.close()
        real_embedder.close()


if __name__ == "__main__":
    evaluate()
