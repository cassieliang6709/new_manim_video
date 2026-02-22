"""
retriever.py

Two retrieval utilities for Visocode:

  RunsRetriever  — semantic search over runs.json for few-shot examples
                   (used by generate_node on first attempt).

  ApiLookup      — static lookup against manim_api_index.json;
                   extracts API names from NameError / AttributeError tracebacks
                   and returns the matching docstring + example
                   (used by debugger_node after execution failure).

Usage:

    # Few-shot retrieval (generate_node)
    retriever = RunsRetriever(Path("manim_output/runs.json"), top_k=2)
    examples  = retriever.get_examples("visualize bubble sort")
    # → [{"prompt": "...", "code": "..."}, ...]

    # API lookup (debugger_node)
    lookup = ApiLookup(Path("manim_api_index.json"))
    snippet = lookup.suggest_for_error("NameError: name 'Write' is not defined")
    # → "[Manim API] Write: Animates writing Text ..."

Dependencies:
    pip install sentence-transformers  (only required by RunsRetriever)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import numpy as np

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentence-transformers model name.  all-MiniLM-L6-v2 is ~80 MB, fast on CPU,
# and gives good semantic similarity for short English/code-adjacent prompts.
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = "all-MiniLM-L6-v2"


class RunsRetriever:
    """Retrieves similar successful Manim scenes from runs.json via embedding similarity.

    The retriever is designed to be **lazy** and **stateless across calls**:
    - The embedding model is loaded on first use (not at import time).
    - ``runs.json`` is re-read on every call so new successful runs are
      immediately available without restarting the server.
    - If ``runs.json`` does not exist, has no successful entries with code,
      or ``sentence-transformers`` is not installed, the retriever silently
      returns an empty list so the pipeline degrades gracefully to zero-shot.

    Args:
        runs_path: Absolute path to the ``runs.json`` file written by ``app.py``.
        top_k:     Maximum number of examples to return.  Defaults to 2.
        model_name: ``sentence-transformers`` model identifier.
    """

    def __init__(
        self,
        runs_path: Path,
        top_k: int = 2,
        model_name: str = _DEFAULT_MODEL,
    ) -> None:
        self.runs_path = Path(runs_path)
        self.top_k = top_k
        self.model_name = model_name
        self._model: Any = None  # lazy-loaded SentenceTransformer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_examples(self, user_prompt: str) -> list[dict[str, str]]:
        """Return up to ``top_k`` similar successful past scenes.

        Each returned dict has two keys:
            ``"prompt"``  — the original user request (≤ 200 chars)
            ``"code"``    — the successful Manim source (≤ 1 200 chars)

        Returns an empty list on cold-start (no data yet) or if
        ``sentence-transformers`` is unavailable.

        Args:
            user_prompt: The current user request.

        Returns:
            Ordered list of similar examples (most similar first).
        """
        candidates = self._load_candidates()
        if not candidates:
            _logger.debug("retriever: no candidates — returning empty (cold start)")
            return []

        try:
            query_vec = self._encode([user_prompt])[0]          # (D,)
            corpus_vecs = self._encode([c["prompt"] for c in candidates])  # (N, D)
        except Exception as exc:
            _logger.warning("retriever: embedding failed — %s", exc)
            return []

        # Cosine similarity (vectors are L2-normalised by encode())
        scores: np.ndarray = corpus_vecs @ query_vec            # (N,)
        top_idx = np.argsort(scores)[::-1][: self.top_k]

        results = [candidates[i] for i in top_idx]
        _logger.info(
            "retriever: returning %d example(s) for prompt '%s...' "
            "(top score=%.3f)",
            len(results),
            user_prompt[:60],
            float(scores[top_idx[0]]) if len(top_idx) else 0.0,
        )
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_candidates(self) -> list[dict[str, str]]:
        """Read runs.json and return entries that have both status=success and code."""
        if not self.runs_path.exists():
            return []
        try:
            with open(self.runs_path, encoding="utf-8") as f:
                runs: list[dict] = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            _logger.warning("retriever: could not read runs.json — %s", exc)
            return []

        candidates = []
        for r in runs:
            if r.get("status") == "success" and r.get("code") and r.get("prompt"):
                candidates.append(
                    {
                        "prompt": r["prompt"],
                        # Truncate to keep LLM context manageable
                        "code": r["code"][:1200],
                    }
                )
        _logger.debug("retriever: loaded %d candidate(s) from runs.json", len(candidates))
        return candidates

    def _encode(self, texts: list[str]) -> np.ndarray:
        """Encode *texts* into L2-normalised vectors using the loaded model.

        Raises:
            ImportError: If ``sentence-transformers`` is not installed.
            RuntimeError: On any model-level error.
        """
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
            except ImportError as exc:
                raise ImportError(
                    "sentence-transformers is required for RAG. "
                    "Install with: pip install sentence-transformers"
                ) from exc
            _logger.info("retriever: loading model '%s'", self.model_name)
            self._model = SentenceTransformer(self.model_name)

        vecs: np.ndarray = self._model.encode(
            texts,
            normalize_embeddings=True,   # cosine sim becomes dot product
            show_progress_bar=False,
        )
        return np.array(vecs, dtype=np.float32)


# ---------------------------------------------------------------------------
# ApiLookup — error-driven Manim API reference lookup
# ---------------------------------------------------------------------------

# Patterns that extract a symbol name from common Python error messages.
_NAMEERROR_RE   = re.compile(r"name '(\w+)' is not defined")
_ATTRERROR_RE   = re.compile(r"has no attribute '(\w+)'")
_IMPORTERROR_RE = re.compile(r"cannot import name '(\w+)'")


class ApiLookup:
    """Looks up Manim API documentation from a curated static index.

    Given a raw traceback string, the lookup:
    1. Extracts symbol names from ``NameError``, ``AttributeError``, and
       ``ImportError`` messages.
    2. Searches ``manim_api_index.json`` for matching entries.
    3. Returns a compact, formatted snippet suitable for injection into the
       ``debugger_hint`` that ``generate_node`` receives on the next retry.

    The index file is loaded once and cached for the lifetime of the object.
    No network access or ML model is required.

    Args:
        index_path: Path to ``manim_api_index.json``.
    """

    def __init__(self, index_path: Path) -> None:
        self.index_path = Path(index_path)
        self._index: list[dict[str, str]] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def suggest_for_error(self, error_text: str) -> str:
        """Extract API names from *error_text* and return matching doc snippets.

        Returns an empty string when no relevant entries are found, so the
        caller can always safely concatenate the result.

        Args:
            error_text: Raw traceback or compressed error string.

        Returns:
            A formatted multi-line string with matching API docs, or ``""``.
        """
        names = self._extract_names(error_text)
        if not names:
            return ""

        snippets: list[str] = []
        for name in names:
            entry = self._lookup(name)
            if entry:
                snippet = (
                    f"[Manim API — {entry['name']}] {entry['note']}\n"
                    f"  Signature: {entry['signature']}\n"
                    f"  Example:   {entry['example'].splitlines()[0]}"
                )
                snippets.append(snippet)
                _logger.info("api_lookup: matched '%s'", name)
            else:
                _logger.debug("api_lookup: no entry for '%s'", name)

        return "\n".join(snippets)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_names(self, error_text: str) -> list[str]:
        """Return unique symbol names found in Python error messages."""
        found: list[str] = []
        for pattern in (_NAMEERROR_RE, _ATTRERROR_RE, _IMPORTERROR_RE):
            found.extend(pattern.findall(error_text))
        # Preserve order, deduplicate
        seen: set[str] = set()
        unique: list[str] = []
        for name in found:
            if name not in seen:
                seen.add(name)
                unique.append(name)
        return unique

    def _lookup(self, name: str) -> dict[str, str] | None:
        """Return the index entry for *name* (case-insensitive), or None."""
        index = self._load_index()
        name_lower = name.lower()
        for entry in index:
            if entry.get("name", "").lower() == name_lower:
                return entry
        return None

    def _load_index(self) -> list[dict[str, str]]:
        """Load and cache the API index JSON."""
        if self._index is not None:
            return self._index
        if not self.index_path.exists():
            _logger.warning("api_lookup: index not found at %s", self.index_path)
            self._index = []
            return self._index
        try:
            with open(self.index_path, encoding="utf-8") as f:
                self._index = json.load(f)
            _logger.debug(
                "api_lookup: loaded %d entries from %s",
                len(self._index),
                self.index_path,
            )
        except (json.JSONDecodeError, OSError) as exc:
            _logger.warning("api_lookup: failed to load index — %s", exc)
            self._index = []
        return self._index
