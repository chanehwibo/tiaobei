from __future__ import annotations

import importlib
import math
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class KylinEmbeddingConfig:
    module_name: str
    factory_name: str | None = None
    method_name: str = "encode"
    response_path: str | None = None
    factory_kwargs: dict[str, Any] | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> KylinEmbeddingConfig:
        module_name = str(value.get("module_name", "")).strip()
        if not module_name:
            raise ValueError("module_name is required")
        factory_kwargs = value.get("factory_kwargs")
        if factory_kwargs is not None and not isinstance(factory_kwargs, dict):
            raise ValueError("factory_kwargs must be an object")
        return cls(
            module_name=module_name,
            factory_name=str(value["factory_name"]).strip() if value.get("factory_name") else None,
            method_name=str(value.get("method_name", "encode")).strip() or "encode",
            response_path=str(value["response_path"]).strip() if value.get("response_path") else None,
            factory_kwargs=dict(factory_kwargs) if factory_kwargs is not None else None,
        )


class KylinEmbeddingProvider:
    """Adapter scaffold for a Kylin embedding SDK client.

    The real SDK is expected to expose a method that accepts text and returns a
    vector directly or a mapping with an ``embedding``/``vector`` field.
    """

    def __init__(
        self,
        client: object,
        method_name: str = "encode",
        response_path: str | None = None,
    ) -> None:
        self.client = client
        self.method_name = method_name
        self.response_path = response_path

    @classmethod
    def from_module(
        cls,
        module_name: str,
        factory_name: str | None = None,
        method_name: str = "encode",
        response_path: str | None = None,
        factory_kwargs: dict[str, Any] | None = None,
    ) -> KylinEmbeddingProvider:
        module = importlib.import_module(module_name)
        if factory_name:
            factory = getattr(module, factory_name, None)
            if not callable(factory):
                raise AttributeError(f"Kylin embedding module does not provide callable {factory_name!r}")
            client = factory(**(factory_kwargs or {}))
        else:
            client = module
        return cls(client=client, method_name=method_name, response_path=response_path)

    @classmethod
    def from_config(cls, config: KylinEmbeddingConfig | dict[str, Any]) -> KylinEmbeddingProvider:
        normalized = config if isinstance(config, KylinEmbeddingConfig) else KylinEmbeddingConfig.from_mapping(config)
        return cls.from_module(
            normalized.module_name,
            factory_name=normalized.factory_name,
            method_name=normalized.method_name,
            response_path=normalized.response_path,
            factory_kwargs=normalized.factory_kwargs,
        )

    def encode(self, text: str) -> list[float]:
        method = getattr(self.client, self.method_name, None)
        if not callable(method):
            raise AttributeError(f"Kylin embedding client does not provide callable {self.method_name!r}")
        raw = method(text)
        if self.response_path:
            raw = _value_at_path(raw, self.response_path)
        vector = _coerce_embedding_vector(raw)
        if not vector:
            raise ValueError("embedding SDK returned an empty vector")
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("embedding SDK returned a non-finite value")
        return normalize(vector)

    def similarity(self, left: str, right: str) -> float:
        return cosine_similarity(self.encode(left), self.encode(right))

    def self_check(self, sample_text: str = "银河麒麟端侧记忆自检") -> dict[str, Any]:
        started = time.perf_counter()
        try:
            vector = self.encode(sample_text)
            norm = math.sqrt(sum(value * value for value in vector))
            return {
                "compatible": True,
                "method_name": self.method_name,
                "response_path": self.response_path,
                "dimension": len(vector),
                "normalized_norm": round(norm, 6),
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            return {
                "compatible": False,
                "method_name": self.method_name,
                "response_path": self.response_path,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }


def check_kylin_embedding(config: KylinEmbeddingConfig | dict[str, Any]) -> dict[str, Any]:
    normalized = config if isinstance(config, KylinEmbeddingConfig) else KylinEmbeddingConfig.from_mapping(config)
    public_config = {
        "module_name": normalized.module_name,
        "factory_name": normalized.factory_name,
        "method_name": normalized.method_name,
        "response_path": normalized.response_path,
        "factory_kwarg_names": sorted((normalized.factory_kwargs or {}).keys()),
    }
    try:
        provider = KylinEmbeddingProvider.from_config(normalized)
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        return {
            "status": "unavailable",
            "compatible": False,
            "config": public_config,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    result = provider.self_check()
    return {
        "status": "ready" if result["compatible"] else "incompatible",
        "config": public_config,
        **result,
    }


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


def _value_at_path(raw: Any, path: str) -> Any:
    current = raw
    for segment in (part for part in path.split(".") if part):
        if isinstance(current, dict):
            if segment not in current:
                raise KeyError(f"embedding response path not found: {path!r}")
            current = current[segment]
        elif isinstance(current, Sequence) and not isinstance(current, str) and segment.isdigit():
            current = current[int(segment)]
        else:
            raise TypeError(f"embedding response path cannot traverse segment {segment!r}")
    return current


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding vectors must have the same dimensions")
    return sum(a * b for a, b in zip(left, right))
