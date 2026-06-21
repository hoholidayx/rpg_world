"""Model loading and invocation for the llama worker process."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class LlamaModelError(Exception):
    """Raised when a llama model cannot be loaded or called."""


def model_cache_key(op: str, model: dict[str, Any]) -> tuple[Any, ...]:
    model_path = str(model.get("model_path") or "")
    if op in {"embed", "embedding_dimension"}:
        return (
            "embedding",
            model_path,
            int(model.get("n_ctx", 32768)),
            int(model.get("n_gpu_layers", 0)),
            int(model.get("n_threads", 4)),
        )
    if op in {"complete", "complete_stream"}:
        return (
            "completion",
            model_path,
            int(model.get("n_ctx", 2048)),
            int(model.get("n_gpu_layers", 0)),
        )
    raise LlamaModelError(f"unsupported op: {op}")


class LlamaModelCache:
    """Lazily load and cache llama.cpp model instances by immutable key."""

    def __init__(self) -> None:
        self._models: dict[tuple[Any, ...], Any] = {}
        self.load_counts: dict[tuple[Any, ...], int] = {}
        self.dimension_cache: dict[tuple[Any, ...], int] = {}

    def embedding_dimension(self, model: dict[str, Any]) -> int:
        key = model_cache_key("embedding_dimension", model)
        if key not in self.dimension_cache:
            vectors = self.embed(model, ["dimension probe"])
            self.dimension_cache[key] = len(vectors[0]) if vectors else 0
        return self.dimension_cache[key]

    def embed(self, model: dict[str, Any], texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        llama = self._get_model("embed", model)
        result = llama.embed(texts)
        if isinstance(result, list) and result and isinstance(result[0], list):
            return result
        return [result]

    def complete(
        self,
        model: dict[str, Any],
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
    ) -> Any:
        llama = self._get_model("complete", model)
        return llama(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or [],
        )

    def complete_stream(
        self,
        model: dict[str, Any],
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
    ):
        llama = self._get_model("complete_stream", model)
        chunks = llama(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or [],
            stream=True,
        )
        for chunk in chunks:
            text = _extract_stream_text(chunk)
            if text:
                yield text

    def _get_model(self, op: str, model: dict[str, Any]) -> Any:
        key = model_cache_key(op, model)
        cached = self._models.get(key)
        if cached is not None:
            return cached

        model_path = Path(str(model.get("model_path") or ""))
        if not model_path.is_file():
            raise LlamaModelError(f"GGUF model not found: {model_path}")
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise LlamaModelError("llama-cpp-python is not installed") from exc

        kind = key[0]
        if kind == "embedding":
            llama = Llama(
                model_path=str(model_path),
                embedding=True,
                n_ctx=int(model.get("n_ctx", 32768)),
                n_gpu_layers=int(model.get("n_gpu_layers", 0)),
                n_threads=int(model.get("n_threads", 4)),
                verbose=bool(model.get("verbose", False)),
            )
        else:
            llama = Llama(
                model_path=str(model_path),
                n_ctx=int(model.get("n_ctx", 2048)),
                n_gpu_layers=int(model.get("n_gpu_layers", 0)),
                verbose=bool(model.get("verbose", False)),
            )
        self._models[key] = llama
        self.load_counts[key] = self.load_counts.get(key, 0) + 1
        return llama


def _extract_stream_text(chunk: Any) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        return chunk
    if not isinstance(chunk, dict):
        return str(chunk)
    choices = chunk.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            text = first.get("text")
            if isinstance(text, str):
                return text
            delta = first.get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                return delta["content"]
    for key in ("content", "text"):
        value = chunk.get(key)
        if isinstance(value, str):
            return value
    return ""
