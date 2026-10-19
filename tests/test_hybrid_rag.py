"""Real Milvus persistence/search; deterministic vectors only for controlled mechanisms."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient
from pymilvus import MilvusClient

from order_api.main import create_app
from order_api.rag import (APIEmbedder, HybridRetriever, RagSettings, RetrievalUnavailable,
                           chunk_documents, reciprocal_rank_fusion, validate_vectors)

DOCS = {"01_冷链.md": "# 冷链规范\n\n## 温控\n温度报警应立即检查设备，医药商品升级人工复核。",
        "02_延迟.md": "# 延迟SOP\n\n## 升级\n滞留超过48小时需升级严重异常工单。"}


def embed(texts):
    # A controlled two-dimensional test double; never used for semantic benchmarks.
    return [[1.0, 0.0] if any(t in text for t in ("冷链", "温度", "医药", "药品失温")) else [0.0, 1.0]
            for text in texts]


@pytest.fixture
def engine(tmp_path):
    retriever = HybridRetriever(RagSettings(uri=str(tmp_path / "vectors.db"), dimensions=2), DOCS, embedder=embed)
    retriever.index()
    yield retriever
    retriever.close()


def test_chunk_sections_overlap_and_identity():
    text = "# 标题\n## 第一节\n" + "甲乙丙丁。" * 100 + "\n## 第二节\n规则B"
    chunks = chunk_documents({"source.md": text}, size=100, overlap=15)
    assert chunks == chunk_documents({"source.md": text}, size=100, overlap=15)
    assert all(len(c.content) <= 100 and c.source == "source.md" for c in chunks)
    assert chunks[0].content[-15:] == chunks[1].content[:15]
    assert chunks[-1].section == "标题 / 第二节"
    changed = chunk_documents({"source.md": text.replace("规则B", "规则C")}, size=100, overlap=15)
    assert changed[-1].chunk_id != chunks[-1].chunk_id
    assert changed[0].chunk_id == chunks[0].chunk_id


def test_rrf_uses_ranks_not_incompatible_raw_scores():
    ranking = reciprocal_rank_fusion([["a", "b", "b"], ["b", "c"]])
    assert ranking[0][0] == "b"
    assert ranking[0][1] == pytest.approx(1 / 62 + 1 / 61)


def test_real_milvus_lite_persists_and_reopens_without_reembedding(tmp_path):
    settings = RagSettings(uri=str(tmp_path / "vectors.db"), dimensions=2)
    first = HybridRetriever(settings, DOCS, embedder=embed)
    assert first.index()["status"] == "indexed"
    collection = first.collection
    first.close()
    second = HybridRetriever(settings, DOCS, embedder=embed)
    try:
        assert second.index()["status"] == "reused"
        assert second.collection == collection
        assert second.search("药品失温")["results"][0]["source"] == "01_冷链.md"
    finally:
        second.close()


def test_hybrid_has_both_channel_scores_and_source(engine):
    result = engine.search("冷链温度报警")
    assert result["retrieval_method"] == "hybrid_bm25_milvus_rrf"
    assert result["degraded"] is False
    evidence = result["results"][0]
    assert evidence["bm25_score"] > 0 and evidence["dense_score"] > .9
    assert evidence["citation"] == "[01_冷链.md / 冷链规范 / 温控]"
    assert result["score_kind"] == "rrf_rank_score"


def test_milvus_schema_keeps_source_and_version_fields(engine):
    description = engine.client.describe_collection(engine.collection)
    fields = {field["name"]: field for field in description["fields"]}
    assert {"id", "vector", "source", "title", "section", "content", "corpus_version", "embedding_model"} <= set(fields)
    assert int(fields["vector"]["params"]["dim"]) == 2
    assert engine.index_info("ready")["index_type"] == "FLAT"


def test_milvus_cosine_distance_field_is_similarity(engine):
    engine.embedder = lambda texts: [[0.8, 0.6] for _ in texts]
    result = engine.dense("controlled-angle")
    assert [value for _, value in result] == pytest.approx([0.8, 0.6])
    engine.settings = replace(engine.settings, min_dense_score=0.9)
    assert engine.dense("controlled-angle") == []


def test_application_uri_is_separate_from_sdk_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    monkeypatch.setenv("MILVUS_URI", "http://sdk-default.example:19530")
    monkeypatch.setenv("LOGISUPPLY_MILVUS_URI", str(tmp_path / "explicit.db"))
    settings = RagSettings.from_env()
    assert settings.uri == str(tmp_path / "explicit.db")


def test_dense_only_evidence_survives_no_keyword_overlap(engine):
    # '药品失温' has lexical character overlap; a truly unseen string tests dense-only flow.
    engine.embedder = lambda texts: [[1., 0.] for _ in texts]
    result = engine.search("unseen-paraphrase")
    assert result["results"][0]["source"] == "01_冷链.md"
    assert result["results"][0]["bm25_score"] is None


@pytest.mark.parametrize("error", [RetrievalUnavailable("embedding_http_error"), RuntimeError("secret body")])
def test_failure_falls_back_without_leaking_exception(engine, error):
    def fail(texts):
        raise error
    engine.embedder = fail
    result = engine.search("冷链温度")
    assert result["degraded"] and result["retrieval_method"] == "chunk_bm25"
    assert result["results"] and "secret" not in str(result)
    engine.embedder = embed
    recovered = engine.search("冷链温度")
    assert not recovered["degraded"] and recovered["retrieval_method"] == "hybrid_bm25_milvus_rrf"


def test_missing_index_and_empty_evidence(tmp_path):
    engine = HybridRetriever(RagSettings(uri=str(tmp_path / "missing.db"), dimensions=2), DOCS, embedder=embed)
    try:
        result = engine.search("zzzxxyy")
        assert result["fallback_reason"] == "index_not_ready" and result["no_evidence"]
    finally:
        engine.close()


def test_corpus_or_model_change_never_queries_old_vectors(engine):
    for cfg, documents in [(replace(engine.settings, model="different-model"), DOCS),
                           (engine.settings, {**DOCS, "03_新.md": "# 新规则\n仅用于新制度"}),
                           (replace(engine.settings, dimensions=3), DOCS)]:
        other = HybridRetriever(cfg, documents, embedder=embed, client=engine.client)
        assert other.collection != engine.collection
        assert other.search("冷链")["fallback_reason"] == "index_not_ready"


def test_failed_embedding_does_not_publish_partial_index(tmp_path):
    settings = RagSettings(uri=str(tmp_path / "vectors.db"), dimensions=2)
    engine = HybridRetriever(settings, DOCS, embedder=lambda texts: [[1., 2., 3.] for _ in texts])
    try:
        with pytest.raises(RetrievalUnavailable):
            engine.index()
        assert not engine.ready()
    finally:
        engine.close()


@pytest.mark.parametrize("vector", [[0., 0.], [1., float("nan")], [float("inf"), 1.], [True, 1], [1.]])
def test_invalid_vectors_rejected(vector):
    with pytest.raises(RetrievalUnavailable):
        validate_vectors([vector], 1, 2)


def test_embedding_api_reorders_indices_and_validates():
    def respond(request):
        assert request.headers["Authorization"] == "Bearer not-real-key"
        return httpx.Response(200, json={"data": [{"index": 1, "embedding": [0, 1]},
                                                  {"index": 0, "embedding": [1, 0]}]})
    client = APIEmbedder(RagSettings(embedding_key="not-real-key", dimensions=2), httpx.MockTransport(respond))
    try:
        assert client(["a", "b"]) == [[1., 0.], [0., 1.]]
    finally:
        client.close()


@pytest.mark.parametrize("body,status", [({"data": [{"index": 0, "embedding": [1, 0]}]}, 429),
                                       ({"data": [{"index": 0, "embedding": [1]}]}, 200),
                                       ({"data": [{"index": 1, "embedding": [1, 0]}]}, 200)])
def test_embedding_api_error_is_sanitized(body, status):
    client = APIEmbedder(RagSettings(embedding_key="not-real-key", dimensions=2),
                         httpx.MockTransport(lambda _: httpx.Response(status, json=body)))
    try:
        with pytest.raises(RetrievalUnavailable):
            client(["a"])
    finally:
        client.close()


def test_milvus_lite_search_is_safe_across_api_threads(engine):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: engine.search("冷链"), range(8)))
    assert all(r["retrieval_method"] == "hybrid_bm25_milvus_rrf" for r in results)


def test_existing_agent_ticket_flow_with_hybrid_search(engine, tmp_path):
    with TestClient(create_app(tmp_path / "tickets.db", tool_key="tool", admin_key="admin", sop_search=engine.search)) as client:
        headers = {"X-API-Key": "tool"}
        result = client.post("/tools/search_sop", headers=headers, json={"query": "冷链异常"}).json()
        assert result["retrieval_method"] == "hybrid_bm25_milvus_rrf"
        context = {"user_id": "demo", "conversation_id": "chat"}
        draft = client.post("/tools/prepare_ticket", headers=headers,
                            json={**context, "order_id": "JD2026003", "summary": "冷链温控异常，请人工检查"}).json()
        body = {**context, "proposal_id": draft["proposal_id"], "user_message": draft["confirmation_phrase"]}
        created = client.post("/tools/create_ticket", headers=headers, json=body).json()
        repeated = client.post("/tools/create_ticket", headers=headers, json=body).json()
        assert created["ticket"]["ticket_id"] == repeated["ticket"]["ticket_id"]
        assert repeated["created"] is False
        ticket_id = created["ticket"]["ticket_id"]
        expected = "open"
        for target in ("processing", "resolved", "closed"):
            reply = client.patch(f"/admin/tickets/{ticket_id}/status", headers={"X-Admin-Key": "admin"},
                                 json={"expected_status": expected, "status": target, "note": "模拟运营处理记录"})
            assert reply.status_code == 200
            expected = target
        found = client.post("/tools/query_ticket", headers=headers, json={"user_id": "demo", "ticket_id": ticket_id}).json()
        assert found["tickets"][0]["status"] == "closed"
        assert len(found["tickets"][0]["events"]) == 4


def test_bm25_explicit_mode_never_calls_embedding(tmp_path):
    def fail(texts):
        raise AssertionError("Embedding should not run")
    engine = HybridRetriever(RagSettings(mode="bm25", uri=str(tmp_path / "unused.db"), dimensions=2), DOCS, embedder=fail)
    try:
        result = engine.search("冷链")
        assert result["retrieval_method"] == "chunk_bm25" and not result["degraded"]
    finally:
        engine.close()
