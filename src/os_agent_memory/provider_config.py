"""One provider configuration for service, persistence and benchmarks."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from queue import Queue, Empty
from threading import Lock, Thread

from .embeddings import HashEmbedding, KylinEmbeddingProvider, normalize, cosine_similarity


def provider_identity(provider):
    return getattr(provider, "identity", {
        "implementation": type(provider).__module__ + "." + type(provider).__qualname__,
        "dimensions": getattr(provider, "dimensions", None), "ngram": getattr(provider, "ngram", None),
    })


class CheckedProvider:
    """Bound one SDK call at a time; a timed-out daemon remains quarantined."""
    def __init__(self, provider, *, dimensions, identity, timeout_seconds=None):
        if dimensions <= 0 or (timeout_seconds is not None and timeout_seconds <= 0):
            raise ValueError("dimensions and timeout must be positive")
        self.provider, self.dimensions, self.identity = provider, dimensions, identity
        self.timeout_seconds = timeout_seconds
        self._busy = Lock()

    def encode(self, text):
        if self.timeout_seconds is None:
            vector = self.provider.encode(text)
        else:
            if not self._busy.acquire(blocking=False):
                raise RuntimeError("embedding worker is still busy after a timeout")
            output = Queue(maxsize=1)
            def call():
                try:
                    output.put((True, self.provider.encode(text)))
                except Exception:
                    output.put((False, "embedding provider call failed"))
                finally:
                    self._busy.release()
            Thread(target=call, daemon=True).start()
            try:
                ok, vector = output.get(timeout=self.timeout_seconds)
            except Empty:
                raise TimeoutError("embedding call timed out") from None
            if not ok:
                raise RuntimeError(vector)
        if len(vector) != self.dimensions or not all(math.isfinite(value) for value in vector):
            raise ValueError("embedding dimension or finite-value contract violated")
        if not any(vector):
            raise ValueError("embedding returned a zero vector")
        return normalize(vector)

    def similarity(self, left, right):
        return cosine_similarity(self.encode(left), self.encode(right))


def create_provider(config=None):
    if config is None:
        return HashEmbedding()
    if isinstance(config, (str, Path)):
        config = json.loads(Path(config).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("embedding configuration must be an object")
    kind = config.get("provider", "hash")
    if kind == "hash":
        dimension = int(config.get("dimensions", 256))
        ngram = int(config.get("ngram", 2))
        if dimension <= 0 or ngram <= 0:
            raise ValueError("hash dimensions and ngram must be positive")
        return HashEmbedding(dimension, ngram)
    if kind not in {"kylin", "kylin-native"} or not config.get("model_version"):
        raise ValueError("kylin provider requires an explicit model_version")
    dimensions = int(config["dimensions"])
    if kind == "kylin-native":
        from .kylin_native import NativeEmbeddingClient
        provider = NativeEmbeddingClient(**config["native"], dimensions=dimensions,
                                         timeout_seconds=config.get("timeout_seconds", 10))
    else:
        provider = KylinEmbeddingProvider.from_config(config["sdk"])
    digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    return CheckedProvider(provider, dimensions=dimensions, identity={
        "provider": kind, "model_version": config["model_version"], "dimensions": dimensions,
        "configuration_sha256": digest,
    }, timeout_seconds=None if kind == "kylin-native" else float(config.get("timeout_seconds", 10)))
