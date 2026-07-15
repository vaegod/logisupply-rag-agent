from evaluation.rag_eval import keyword_hit, percentile_95, summarize_results


def test_keyword_hit_uses_expected_terms() -> None:
    assert keyword_hit("建议拍照、登记异常工单后判断赔付责任", "拍照 登记 赔付") == 1.0
    assert keyword_hit("建议先拍照留证", "拍照 登记 赔付") == 1 / 3


def test_percentile_95_uses_nearest_rank() -> None:
    assert percentile_95([1, 2, 3, 4, 5]) == 5
    assert percentile_95([]) == 0.0


def test_summarize_results_separates_api_and_answer_quality() -> None:
    results = [
        {
            "type": "knowledge",
            "api_success": "是",
            "passed": "是",
            "latency_ms": 100.0,
        },
        {
            "type": "knowledge",
            "api_success": "是",
            "passed": "否",
            "latency_ms": 300.0,
        },
        {
            "type": "order",
            "api_success": "否",
            "passed": "否",
            "latency_ms": 10.0,
        },
    ]

    summary = summarize_results(results)

    assert summary["api_success_rate"] == 0.6667
    assert summary["keyword_pass_rate"] == 0.3333
    assert summary["average_latency_ms"] == 200.0
    assert summary["per_type"]["knowledge"]["keyword_pass_rate"] == 0.5
