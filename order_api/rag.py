"""Section-level BM25 + Milvus dense retrieval, fused by reciprocal rank.

Milvus Lite supports local tests; LOGISUPPLY_MILVUS_URI also accepts a standalone server.
Indexing is explicit: never call an embedding model
for the entire corpus from a user search request.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable
from uuid import NAMESPACE_URL, uuid5

import httpx
from pymilvus import MilvusClient, DataType

from .knowledge import BM25Index, DOCS_DIR

LOG = logging.getLogger(__name__)
CHUNK_VERSION = "heading-v1-700-80"
STORE_VERSION = "milvus-flat-cosine-v1"


class RetrievalUnavailable(RuntimeError):
    """A public, credential-free error code, never an upstream response body."""


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source: str
    title: str
    section: str
    content: str

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.section}\n{self.content}"


def chunk_documents(documents: dict[str, str], size: int = 700, overlap: int = 80) -> list[Chunk]:
    if size < 100 or not 0 <= overlap < size:
        raise ValueError("Invalid chunk size/overlap")
    chunks = []
    for source, text in sorted(documents.items()):
        title, headings, body = source, [], []

        def flush():
            content = "\n".join(body).strip()
            if not content:
                return
            section = " / ".join(value for _, value in headings) or title
            start = 0
            while start < len(content):
                end = min(start + size, len(content))
                if end < len(content):
                    boundary = max(content.rfind(mark, start + size // 2, end) for mark in ("\n", "。", "；"))
                    if boundary >= start + size // 2:
                        end = boundary + 1
                piece = content[start:end].strip()
                identity = json.dumps([CHUNK_VERSION, source, section, start, piece], ensure_ascii=False)
                chunks.append(Chunk(str(uuid5(NAMESPACE_URL, identity)), source, title, section, piece))
                if end == len(content):
                    break
                start = end - overlap

        for line in text.splitlines():
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if match:
                flush()
                body = []
                level, name = len(match[1]), match[2]
                if level == 1:
                    title = name
                headings = [(depth, heading) for depth, heading in headings if depth < level]
                headings.append((level, name))
            else:
                body.append(line)
        flush()
    return chunks


@dataclass(frozen=True)
class RagSettings:
    mode: str = "hybrid"
    uri: str = str(Path(__file__).parent / "data/milvus.db")
    token: str = field(default="", repr=False)
    embedding_url: str = "https://api.siliconflow.cn/v1"
    embedding_key: str = field(default="", repr=False)
    model: str = "BAAI/bge-m3"
    dimensions: int = 1024
    timeout: float = 8.0
    min_dense_score: float = 0.45

    def __post_init__(self):
        if self.mode not in {"hybrid", "bm25"}:
            raise ValueError("RAG_MODE must be hybrid or bm25")
        if not 1 <= self.dimensions <= 16384 or not 0 < self.timeout <= 60:
            raise ValueError("Invalid embedding dimensions/timeout")
        if not -1 <= self.min_dense_score <= 1 or not self.model.strip():
            raise ValueError("Invalid dense threshold/model")

    @classmethod
    def from_env(cls):
        mount = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
        uri = os.getenv("LOGISUPPLY_MILVUS_URI", str(Path(mount) / "milvus.db") if mount else cls.uri)
        if mount and not uri.startswith(("http://", "https://")) and not Path(uri).resolve().is_relative_to(Path(mount).resolve()):
            raise ValueError("Local LOGISUPPLY_MILVUS_URI must be inside the persistent volume")
        return cls(mode=os.getenv("RAG_MODE", "hybrid"), uri=uri,
                   token=os.getenv("LOGISUPPLY_MILVUS_TOKEN", ""),
                   embedding_url=os.getenv("EMBEDDING_BASE_URL", cls.embedding_url).rstrip("/"),
                   embedding_key=os.getenv("EMBEDDING_API_KEY", ""),
                   model=os.getenv("EMBEDDING_MODEL", cls.model),
                   dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "1024")),
                   timeout=float(os.getenv("RAG_TIMEOUT_SECONDS", "8")),
                   min_dense_score=float(os.getenv("RAG_MIN_DENSE_SCORE", "0.45")))


class APIEmbedder:
    def __init__(self, settings: RagSettings, transport=None):
        self.settings = settings
        self.client = httpx.Client(timeout=httpx.Timeout(settings.timeout, connect=min(3, settings.timeout)), transport=transport)

    def __call__(self, texts: list[str]) -> list[list[float]]:
        cfg = self.settings
        if not cfg.embedding_key:
            raise RetrievalUnavailable("embedding_not_configured")
        try:
            response = self.client.post(cfg.embedding_url + "/embeddings",
                                        headers={"Authorization": "Bearer " + cfg.embedding_key},
                                        json={"model": cfg.model, "input": texts, "encoding_format": "float"})
            if response.status_code != 200:
                raise RetrievalUnavailable("embedding_http_error")
            data = response.json()["data"]
            if len(data) != len(texts):
                raise ValueError("count")
            indexed = {row["index"]: row["embedding"] for row in data}
            if set(indexed) != set(range(len(texts))) or len(indexed) != len(data):
                raise ValueError("indices")
            return validate_vectors([indexed[i] for i in range(len(texts))], len(texts), cfg.dimensions)
        except RetrievalUnavailable:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, OverflowError) as exc:
            raise RetrievalUnavailable("embedding_invalid_or_unavailable") from None

    def close(self):
        self.client.close()


def validate_vectors(vectors, count: int, dimensions: int) -> list[list[float]]:
    if len(vectors) != count:
        raise RetrievalUnavailable("embedding_invalid_vectors")
    validated = []
    for vector in vectors:
        if len(vector) != dimensions:
            raise RetrievalUnavailable("embedding_invalid_vectors")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in vector):
            raise RetrievalUnavailable("embedding_invalid_vectors")
        values = [float(value) for value in vector]
        if not all(math.isfinite(value) for value in values) or not any(values):
            raise RetrievalUnavailable("embedding_invalid_vectors")
        validated.append(values)
    return validated


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(dict.fromkeys(ranking), 1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


class HybridRetriever:
    def __init__(self, settings: RagSettings, documents: dict[str, str], *, embedder: Callable | None = None,
                 client: MilvusClient | None = None):
        self.settings = settings
        self.chunks = chunk_documents(documents)
        self.by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        self.bm25 = BM25Index({chunk.chunk_id: chunk.text for chunk in self.chunks})
        identity = json.dumps([CHUNK_VERSION, STORE_VERSION, settings.model, settings.dimensions, settings.embedding_url,
                               [asdict(c) for c in self.chunks]], ensure_ascii=False, sort_keys=True)
        self.fingerprint = hashlib.sha256(identity.encode()).hexdigest()
        self.collection = "logisupply_sop_" + self.fingerprint[:24]
        self.embedder = embedder if embedder is not None else APIEmbedder(settings)
        self._client = client
        self._lock = threading.RLock()

    @property
    def client(self):
        if self._client is None:
            cfg = self.settings
            if not cfg.uri.startswith(("http://", "https://")):
                Path(cfg.uri).parent.mkdir(parents=True, exist_ok=True)
            self._client = MilvusClient(uri=cfg.uri, token=cfg.token, timeout=cfg.timeout)
        return self._client

    def index(self) -> dict:
        """Versioned collection: a new model/corpus never queries an old index."""
        with self._lock:
            if not self.chunks:
                raise RetrievalUnavailable("empty_corpus")
            if self.ready():
                return self.index_info("reused")
            vectors = []
            for start in range(0, len(self.chunks), 16):
                batch = self.chunks[start:start + 16]
                vectors.extend(validate_vectors(self.embedder([c.text for c in batch]), len(batch), self.settings.dimensions))
            if not self.client.has_collection(self.collection, timeout=self.settings.timeout):
                schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
                schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=36)
                schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self.settings.dimensions)
                for name, length in (("source", 1024), ("title", 2048), ("section", 4096),
                                     ("content", 16384), ("corpus_version", 64), ("embedding_model", 256)):
                    schema.add_field(name, DataType.VARCHAR, max_length=length)
                indexes = MilvusClient.prepare_index_params()
                indexes.add_index(field_name="vector", index_type="FLAT", metric_type="COSINE")
                self.client.create_collection(self.collection, schema=schema, index_params=indexes,
                                              consistency_level="Strong", timeout=max(30, self.settings.timeout))
            for start in range(0, len(self.chunks), 64):
                self.client.upsert(self.collection, data=[{
                    "id": c.chunk_id, "vector": v, "source": c.source, "title": c.title,
                    "section": c.section, "content": c.content, "corpus_version": self.fingerprint,
                    "embedding_model": self.settings.model}
                    for c, v in zip(self.chunks[start:start + 64], vectors[start:start + 64])], timeout=self.settings.timeout)
            self.client.flush(self.collection, timeout=max(30, self.settings.timeout))
            if not self.ready():
                raise RetrievalUnavailable("index_incomplete")
            return self.index_info("indexed")

    def ready(self) -> bool:
        if not self.client.has_collection(self.collection, timeout=self.settings.timeout):
            return False
        self.client.load_collection(self.collection, timeout=self.settings.timeout)
        # Statistics may exclude growing segments; use a strongly consistent
        # aggregate query instead of treating get_collection_stats as exact.
        rows = self.client.query(self.collection, filter="", output_fields=["count(*)"],
                                 consistency_level="Strong", timeout=self.settings.timeout)
        return bool(rows) and int(rows[0]["count(*)"]) == len(self.chunks)

    def index_info(self, status: str) -> dict:
        return {"status": status, "collection": self.collection, "corpus_version": self.fingerprint,
                "documents": len({c.source for c in self.chunks}), "chunks": len(self.chunks),
                "embedding_model": self.settings.model, "dimensions": self.settings.dimensions,
                "vector_backend": "milvus_server" if self.settings.uri.startswith(("http://", "https://")) else "milvus_lite",
                "index_type": "FLAT", "metric_type": "COSINE", "consistency": "Strong"}

    def dense(self, query: str, limit: int = 12) -> list[tuple[str, float]]:
        if isinstance(self.embedder, APIEmbedder) and not self.settings.embedding_key:
            raise RetrievalUnavailable("embedding_not_configured")
        if not self.ready():
            raise RetrievalUnavailable("index_not_ready")
        vector = validate_vectors(self.embedder([query]), 1, self.settings.dimensions)[0]
        result = self.client.search(self.collection, data=[vector], anns_field="vector", limit=limit,
                                     search_params={"metric_type": "COSINE", "params": {}},
                                     consistency_level="Strong", timeout=self.settings.timeout)
        return [(str(point["id"]), float(point["distance"])) for point in result[0]
                if str(point["id"]) in self.by_id and float(point["distance"]) >= self.settings.min_dense_score]

    def search(self, query: str, top_k: int = 3) -> dict:
        if not query.strip() or len(query) > 500 or not 1 <= top_k <= 5:
            raise ValueError("Invalid search request")
        with self._lock:
            lexical = [(key, score) for key, score in self.bm25.search(query) if score > 0][:12]
            dense, fallback = [], None
            if self.settings.mode == "hybrid":
                try:
                    dense = self.dense(query)
                except Exception as exc:
                    fallback = str(exc) if isinstance(exc, RetrievalUnavailable) else "vector_store_unavailable"
                    LOG.warning("SOP dense retrieval unavailable: %s", fallback)
            lists = [[key for key, _ in lexical], [key for key, _ in dense]]
            hybrid = self.settings.mode == "hybrid" and fallback is None
            ranking = reciprocal_rank_fusion(lists) if hybrid else lexical
            lexical_scores, dense_scores = dict(lexical), dict(dense)
            results = []
            for key, score in ranking[:top_k]:
                chunk = self.by_id[key]
                results.append({**asdict(chunk), "score": round(score, 6), "truncated": False,
                                "citation": f"[{chunk.source} / {chunk.section}]",
                                "bm25_score": lexical_scores.get(key), "dense_score": dense_scores.get(key)})
            return {"retrieval_method": "hybrid_bm25_milvus_rrf" if hybrid else "chunk_bm25",
                    "query": query, "degraded": fallback is not None, "fallback_reason": fallback,
                    "corpus_version": self.fingerprint, "embedding_model": self.settings.model if hybrid else None,
                    "score_kind": "rrf_rank_score" if hybrid else "bm25_score", "no_evidence": not results,
                    "results": results}

    def close(self):
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
            close = getattr(self.embedder, "close", None)
            if close:
                close()


def load_retriever(settings: RagSettings | None = None) -> HybridRetriever:
    documents = {p.name: p.read_text(encoding="utf-8") for p in sorted(DOCS_DIR.glob("[0-9][0-9]_*.md"))}
    return HybridRetriever(settings or RagSettings.from_env(), documents)
