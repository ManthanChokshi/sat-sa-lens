"""Local-only text embeddings for note similarity (detector D04).

Offline guarantees:
  * the sentence-transformers model is loaded from a bundled local folder only
    (app.config.MODEL_DIR); HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE are set before
    the library is imported, so it can never reach the network;
  * if that folder is absent the app does NOT silently phone home. It either
    raises (SATSA_REQUIRE_MODEL=1, the packaged default) or falls back to a
    deterministic character n-gram TF-IDF vectoriser, and every finding records
    which method was used.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from app.config import MODEL_DIR

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

REQUIRE_MODEL = os.environ.get("SATSA_REQUIRE_MODEL", "0") == "1"

MISSING_MODEL_MESSAGE = (
    f"Sentence-transformers model folder not found at {MODEL_DIR}.\n"
    "Run this ONCE on a machine with internet access:\n"
    "    python scripts/download_model.py\n"
    "then ship the models/ folder with the deployment. The application never "
    "downloads anything at runtime."
)

_MODEL = None
_MODEL_TRIED = False


@dataclass
class EmbeddingResult:
    vectors: np.ndarray  # L2-normalised, shape (n, d)
    method: str
    model_name: str
    dimensions: int


def model_available() -> bool:
    return MODEL_DIR.exists() and any(MODEL_DIR.iterdir()) if MODEL_DIR.exists() else False


def _load_model():
    global _MODEL, _MODEL_TRIED
    if _MODEL is not None or _MODEL_TRIED:
        return _MODEL
    _MODEL_TRIED = True
    if not model_available():
        if REQUIRE_MODEL:
            raise RuntimeError(MISSING_MODEL_MESSAGE)
        return None
    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - optional heavy dependency
        if REQUIRE_MODEL:
            raise RuntimeError(
                "sentence-transformers is not installed. Install the optional ML "
                "extras: pip install -r requirements-ml.txt"
            ) from exc
        return None
    _MODEL = SentenceTransformer(str(MODEL_DIR), device="cpu", local_files_only=True)
    return _MODEL


def _tfidf_vectors(texts: Sequence[str]) -> EmbeddingResult:
    """Deterministic lexical fallback: character n-grams + TF-IDF + SVD."""
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=1, max_features=60_000,
        sublinear_tf=True,
    )
    matrix = vec.fit_transform(texts)
    dim = int(min(256, max(2, min(matrix.shape) - 1)))
    if matrix.shape[0] > 2 and matrix.shape[1] > 2:
        svd = TruncatedSVD(n_components=dim, random_state=42)
        dense = svd.fit_transform(matrix)
    else:  # pragma: no cover - degenerate tiny inputs
        dense = matrix.toarray()
    norms = np.linalg.norm(dense, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return EmbeddingResult(
        vectors=dense / norms,
        method="tfidf_char_ngram_fallback",
        model_name="char_wb(3,5)+TruncatedSVD",
        dimensions=dense.shape[1],
    )


def embed(texts: Sequence[str], batch_size: int = 128) -> EmbeddingResult:
    """Embed texts with the bundled model, or the deterministic fallback."""
    if not texts:
        return EmbeddingResult(np.zeros((0, 1)), "empty", "none", 0)
    model = _load_model()
    if model is None:
        return _tfidf_vectors(list(texts))
    vectors = model.encode(
        list(texts),
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return EmbeddingResult(
        vectors=np.asarray(vectors, dtype=np.float32),
        method="sentence_transformers_local",
        model_name=MODEL_DIR.name,
        dimensions=int(vectors.shape[1]),
    )


def greedy_cosine_clusters(
    vectors: np.ndarray, threshold: float = 0.92
) -> list[int]:
    """Assign each row to the first cluster whose centroid exceeds `threshold`.

    Deterministic (input order decides) and O(n * clusters). The centroid matrix
    is preallocated so no per-row reallocation happens - that keeps the pass fast
    even when almost every note is unique.
    """
    n = vectors.shape[0]
    if n == 0:
        return []
    vectors = np.ascontiguousarray(vectors, dtype=np.float32)
    dim = vectors.shape[1]
    centroids = np.zeros((n, dim), dtype=np.float32)
    labels = np.full(n, -1, dtype=int)
    k = 0
    for i in range(n):
        v = vectors[i]
        if k:
            sims = centroids[:k] @ v
            best = int(np.argmax(sims))
            if sims[best] >= threshold:
                labels[i] = best
                c = centroids[best] + (v - centroids[best]) * 0.15
                norm = float(np.linalg.norm(c))
                centroids[best] = c / (norm if norm else 1.0)
                continue
        centroids[k] = v
        labels[i] = k
        k += 1
    return labels.tolist()
