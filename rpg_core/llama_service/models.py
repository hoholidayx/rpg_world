"""Model loading and invocation for the llama worker process."""

from __future__ import annotations

import math
from pathlib import Path

from ..common_types import (
    LlamaCacheKey,
    LlamaLogits,
    JsonValue,
    LlamaModelConfig,
    LlamaModelHandle,
    LlamaResponsePayload,
)


class LlamaModelError(Exception):
    """Raised when a llama model cannot be loaded or called."""


def model_cache_key(op: str, model: LlamaModelConfig) -> LlamaCacheKey:
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
    if op == "rerank":
        return (
            "rerank",
            model_path,
            int(model.get("n_ctx", 4096)),
            int(model.get("n_gpu_layers", 0)),
        )
    raise LlamaModelError(f"unsupported op: {op}")


class LlamaModelCache:
    """Lazily load and cache llama.cpp model instances by immutable key."""

    def __init__(self) -> None:
        self._models: dict[LlamaCacheKey, LlamaModelHandle] = {}
        self.load_counts: dict[LlamaCacheKey, int] = {}
        self.dimension_cache: dict[LlamaCacheKey, int] = {}

    def embedding_dimension(self, model: LlamaModelConfig) -> int:
        key = model_cache_key("embedding_dimension", model)
        if key not in self.dimension_cache:
            vectors = self.embed(model, ["dimension probe"])
            self.dimension_cache[key] = len(vectors[0]) if vectors else 0
        return self.dimension_cache[key]

    def embed(self, model: LlamaModelConfig, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        llama = self._get_model("embed", model)
        result = llama.embed(texts)
        if isinstance(result, list) and result and isinstance(result[0], list):
            return result
        return [result]

    def complete(
        self,
        model: LlamaModelConfig,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
    ) -> LlamaResponsePayload:
        llama = self._get_model("complete", model)
        return llama(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or [],
        )

    def complete_stream(
        self,
        model: LlamaModelConfig,
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

    def rerank(
        self,
        model: LlamaModelConfig,
        query: str,
        documents: list[str],
        *,
        instruction: str,
        max_length: int,
    ) -> list[dict[str, float]]:
        if not documents:
            return []
        llama = self._get_model("rerank", model)
        yes_token_id = _first_token_id(llama, "yes")
        no_token_id = _first_token_id(llama, "no")
        results: list[dict[str, float]] = []
        for document in documents:
            tokens = _build_qwen_rerank_tokens(
                llama,
                instruction=instruction,
                query=query,
                document=document,
                max_length=max_length,
            )
            if not tokens:
                results.append({"score": 0.0, "yes_logit": 0.0, "no_logit": 0.0})
                continue
            _reset_llama(llama)
            llama.eval(tokens)
            logits = _last_logits(llama, len(tokens))
            yes_logit = _logit_at(logits, yes_token_id)
            no_logit = _logit_at(logits, no_token_id)
            results.append(
                {
                    "score": _yes_probability(yes_logit, no_logit),
                    "yes_logit": yes_logit,
                    "no_logit": no_logit,
                }
            )
        return results

    def _get_model(self, op: str, model: LlamaModelConfig) -> LlamaModelHandle:
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
        elif kind == "completion":
            llama = Llama(
                model_path=str(model_path),
                n_ctx=int(model.get("n_ctx", 2048)),
                n_gpu_layers=int(model.get("n_gpu_layers", 0)),
                verbose=bool(model.get("verbose", False)),
            )
        else:
            llama = Llama(
                model_path=str(model_path),
                n_ctx=int(model.get("n_ctx", 4096)),
                n_gpu_layers=int(model.get("n_gpu_layers", 0)),
                logits_all=True,
                verbose=bool(model.get("verbose", False)),
            )
        self._models[key] = llama
        self.load_counts[key] = self.load_counts.get(key, 0) + 1
        return llama


QWEN_RERANK_SYSTEM_PROMPT = (
    "Judge whether the Document meets the requirements based on the Query and the Instruct provided. "
    'Note that the answer can only be "yes" or "no".'
)
QWEN_RERANK_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


def build_qwen_rerank_prompt(*, instruction: str, query: str, document: str) -> str:
    return (
        f"<|im_start|>system\n{QWEN_RERANK_SYSTEM_PROMPT}<|im_end|>\n"
        "<|im_start|>user\n"
        f"<Instruct>: {instruction}\n"
        f"<Query>: {query}\n"
        f"<Document>: {document}"
        f"{QWEN_RERANK_SUFFIX}"
    )


def _build_qwen_rerank_tokens(
    llama: LlamaModelHandle,
    *,
    instruction: str,
    query: str,
    document: str,
    max_length: int,
) -> list[int]:
    max_length = max(1, int(max_length or 4096))
    prefix = (
        f"<|im_start|>system\n{QWEN_RERANK_SYSTEM_PROMPT}<|im_end|>\n"
        "<|im_start|>user\n"
        f"<Instruct>: {instruction}\n"
        f"<Query>: {query}\n"
        "<Document>: "
    )
    suffix = QWEN_RERANK_SUFFIX
    prefix_tokens = _tokenize(llama, prefix, add_bos=True)
    suffix_tokens = _tokenize(llama, suffix, add_bos=False)
    document_tokens = _tokenize(llama, document, add_bos=False)
    budget = max_length - len(prefix_tokens) - len(suffix_tokens)
    if budget < 0:
        return (prefix_tokens + suffix_tokens)[-max_length:]
    return prefix_tokens + document_tokens[:budget] + suffix_tokens


def _tokenize(llama: LlamaModelHandle, text: str, *, add_bos: bool) -> list[int]:
    raw = text.encode("utf-8")
    try:
        return list(llama.tokenize(raw, add_bos=add_bos, special=True))
    except TypeError:
        return list(llama.tokenize(raw, add_bos=add_bos))


def _first_token_id(llama: LlamaModelHandle, text: str) -> int:
    tokens = _tokenize(llama, text, add_bos=False)
    if not tokens:
        raise LlamaModelError(f"tokenizer returned no token for label {text!r}")
    return int(tokens[0])


def _reset_llama(llama: LlamaModelHandle) -> None:
    reset = getattr(llama, "reset", None)
    if callable(reset):
        reset()


def _last_logits(llama: LlamaModelHandle, token_count: int) -> LlamaLogits:
    scores = getattr(llama, "scores", None)
    if scores is None:
        raise LlamaModelError("llama model did not expose scores; load rerank model with logits_all=True")
    if token_count <= 0:
        raise LlamaModelError(f"invalid rerank token count: {token_count}")
    try:
        score_count = len(scores)
    except TypeError as exc:
        raise LlamaModelError("llama scores are not indexable") from exc
    if score_count <= 0:
        raise LlamaModelError("llama scores are empty")
    index = token_count - 1
    try:
        if index < score_count:
            return scores[index]
        return scores[-1]
    except IndexError as exc:
        raise LlamaModelError(f"llama scores index out of range: token_count={token_count} scores={score_count}") from exc


def _logit_at(logits: LlamaLogits, token_id: int) -> float:
    try:
        return float(logits[token_id])
    except Exception as exc:
        raise LlamaModelError(f"logit missing for token id {token_id}") from exc


def _yes_probability(yes_logit: float, no_logit: float) -> float:
    high = max(yes_logit, no_logit)
    yes_exp = math.exp(yes_logit - high)
    no_exp = math.exp(no_logit - high)
    denom = yes_exp + no_exp
    if denom <= 0.0:
        return 0.0
    return max(0.0, min(1.0, yes_exp / denom))


def _extract_stream_text(chunk: JsonValue) -> str:
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
