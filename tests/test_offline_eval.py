from evaluation.offline_eval import (
    BM25Index,
    build_report,
    classify_intent,
    extract_order_id,
    load_documents,
    tokenize,
)


def test_tokenize_mixed_chinese_and_ascii() -> None:
    tokens = tokenize("订单 JD2026001 温度异常")

    assert "jd2026001" in tokens
    assert "温度" in tokens
    assert "异常" in tokens


def test_extract_order_id_is_case_insensitive() -> None:
    assert extract_order_id("帮我查 jd2026001") == "JD2026001"
    assert extract_order_id("没有订单号") is None


def test_rule_router_distinguishes_order_and_exception() -> None:
    assert classify_intent("仓储入库流程是什么？") == "knowledge"
    assert classify_intent("JD2026001 到哪了？") == "order"
    assert classify_intent("JD2026002 延迟了怎么处理？") == "exception"
    assert classify_intent("JD2026003 出现温度异常如何处理？") == "exception"
    assert classify_intent("订单不存在时应该怎么提示？") == "exception"


def test_bm25_returns_cold_chain_document_first() -> None:
    index = BM25Index(load_documents())
    ranking = index.search("冷链运输出现温度报警怎么办？")

    assert ranking[0][0] == "03_冷链运输规范.md"


def test_full_offline_baseline_meets_minimum_thresholds() -> None:
    report, _, _ = build_report()

    assert report["document_count"] == 10
    assert report["retrieval"]["recall_at_3"] >= 0.80
    assert report["routing_and_tools"]["intent_accuracy"] >= 0.90
    assert report["routing_and_tools"]["known_order_tool_success_rate"] == 1.0
