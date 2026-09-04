from __future__ import annotations

import importlib
import math
import re
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from .schemas import stable_id


class EmbeddingProvider(Protocol):
    """Minimal embedding interface used by retrieval and conflict detection."""

    def encode(self, text: str) -> list[float]:
        ...

    def similarity(self, left: str, right: str) -> float:
        ...


class HashEmbedding:
    """Lightweight local embedding fallback based on character n-gram hashing."""

    def __init__(self, dimensions: int = 256, ngram: int = 2) -> None:
        self.dimensions = dimensions
        self.ngram = ngram

    def encode(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            bucket = int(stable_id(token), 16) % self.dimensions
            vector[bucket] += 1.0
        return normalize(vector)

    def similarity(self, left: str, right: str) -> float:
        return cosine_similarity(self.encode(left), self.encode(right))

    def _tokens(self, text: str) -> list[str]:
        compact = re.sub(r"\s+", "", text.lower())
        if not compact:
            return []
        if len(compact) <= self.ngram:
            return [compact]
        return [compact[index : index + self.ngram] for index in range(len(compact) - self.ngram + 1)]


class CallableEmbeddingProvider:
    """Adapter for an external SDK function that returns dense vectors."""

    def __init__(self, encode_fn: Callable[[str], Sequence[float]]) -> None:
        self.encode_fn = encode_fn

    def encode(self, text: str) -> list[float]:
        return normalize([float(value) for value in self.encode_fn(text)])

    def similarity(self, left: str, right: str) -> float:
        return cosine_similarity(self.encode(left), self.encode(right))


class KylinEmbeddingProvider:
    """Adapter scaffold for a Kylin embedding SDK client.

    The real SDK is expected to expose a method that accepts text and returns a
    vector directly or a mapping with an ``embedding``/``vector`` field.
    """

    def __init__(self, client: object, method_name: str = "encode") -> None:
        self.client = client
        self.method_name = method_name

    @classmethod
    def from_module(
        cls,
        module_name: str,
        factory_name: str | None = None,
        method_name: str = "encode",
    ) -> KylinEmbeddingProvider:
        module = importlib.import_module(module_name)
        client = getattr(module, factory_name)() if factory_name else module
        return cls(client=client, method_name=method_name)

    def encode(self, text: str) -> list[float]:
        method = getattr(self.client, self.method_name, None)
        if not callable(method):
            raise AttributeError(f"Kylin embedding client does not provide callable {self.method_name!r}")
        return normalize(_coerce_embedding_vector(method(text)))

    def similarity(self, left: str, right: str) -> float:
        return cosine_similarity(self.encode(left), self.encode(right))


def normalize(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return [0.0 for _value in vector]
    return [value / norm for value in vector]


def _coerce_embedding_vector(raw: Any) -> list[float]:
    if isinstance(raw, dict):
        for key in ("embedding", "vector"):
            if key in raw:
                raw = raw[key]
                break

    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise TypeError("embedding SDK result must be a numeric sequence or a mapping containing one")
    return [float(value) for value in raw]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding vectors must have the same dimensions")
    return sum(a * b for a, b in zip(left, right))
