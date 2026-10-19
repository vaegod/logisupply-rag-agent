"""BM25 baseline primitives and the lazy hybrid SOP retrieval entry point."""
from __future__ import annotations

import math
import atexit
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache

DOCS_DIR = Path(__file__).parents[1] / "docs"


def tokenize(text: str) -> list[str]:
    normalized = text.lower()
    tokens = re.findall(r"[a-z0-9]+", normalized)
    for segment in re.findall(r"[\u4e00-\u9fff]+", normalized):
        tokens.extend(segment)
        tokens.extend(segment[index:index + 2] for index in range(len(segment) - 1))
    return tokens


@dataclass
class BM25Index:
    documents: dict[str, str]
    k1: float = 1.5
    b: float = 0.75

    def __post_init__(self):
        self.doc_tokens = {name: tokenize(content) for name, content in self.documents.items()}
        self.doc_freq = Counter()
        for tokens in self.doc_tokens.values():
            self.doc_freq.update(set(tokens))
        self.doc_count = len(self.doc_tokens)
        self.avg_doc_length = sum(map(len, self.doc_tokens.values())) / self.doc_count if self.doc_count else 0.0

    def score(self, query: str, document_name: str) -> float:
        tokens = self.doc_tokens[document_name]
        frequencies = Counter(tokens)
        score = 0.0
        for token in tokenize(query):
            frequency = frequencies[token]
            if not frequency:
                continue
            df = self.doc_freq[token]
            idf = math.log(1 + (self.doc_count - df + 0.5) / (df + 0.5))
            denominator = frequency + self.k1 * (1 - self.b + self.b * len(tokens) / self.avg_doc_length)
            score += idf * frequency * (self.k1 + 1) / denominator
        return score

    def search(self, query: str) -> list[tuple[str, float]]:
        return sorted(((name, self.score(query, name)) for name in self.documents),
                      key=lambda item: (-item[1], item[0]))


def load_documents() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8")
            for path in sorted(DOCS_DIR.glob("[0-9][0-9]_*.md"))}


@lru_cache(maxsize=1)
def get_retriever():
    from .rag import load_retriever
    engine = load_retriever()
    atexit.register(engine.close)
    return engine


def search_sop(query: str, top_k: int = 3) -> dict:
    return get_retriever().search(query, top_k)
