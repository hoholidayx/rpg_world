"""FastAPI boundary for the standalone LLM runtime."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import secrets
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from loguru import logger

from llm_client.codec import chunk_to_wire, response_to_wire
from llm_service.base_provider import DocumentScoreProvider, LLMProvider
from llm_service.config import (
    get_biz_config,
    list_provider_options,
    load_llm_settings,
    resolve_biz_config,
)
from llm_service.keys import LLM_KIND_SPEECH
from llm_service.manager import LLMManager
from llm_service.errors import LLMInputModalityUnsupportedError
from llm_service.pointwise import score_documents_with_chat
from llm_service.schemas import (
    LLMCatalogResponse,
    LLMChatRequest,
    LLMChatResponse,
    LLMDocumentScoreResponse,
    LLMEmbeddingDimensionResponse,
    LLMEmbeddingRequest,
    LLMEmbeddingResponse,
    LLMHealthResponse,
    LLMProviderOptionResponse,
    LLMRerankRequest,
    LLMRerankResponse,
    LLMSpeechProfileResponse,
    LLMSpeechRequest,
)
from llm_service.settings import settings

_config_loaded = False


def _prefix() -> str:
    return settings.service.api_prefix


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config_loaded
    auth = settings.auth
    if auth.uses_default_token:
        logger.warning(
            "LLM service token environment variable {} is not set; "
            "using the built-in local default token. Configure the environment "
            "variable for non-local deployments.",
            auth.token_env,
        )
    _validate_config()
    _config_loaded = True
    try:
        yield
    finally:
        _config_loaded = False
        await LLMManager.areset()


app = FastAPI(title="RPG World LLM Service", lifespan=lifespan)


@app.middleware("http")
async def assign_request_id(request: Request, call_next):  # noqa: ANN001, ANN201
    request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["x-request-id"] = request.state.request_id
    return response


def _authorize(authorization: str | None = Header(default=None)) -> None:
    expected = settings.auth.token
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=401,
            detail={"errorCode": "LLM_AUTH_FAILED", "message": "invalid LLM service bearer token"},
        )


@app.get(f"{_prefix()}/health", response_model=LLMHealthResponse)
async def health() -> LLMHealthResponse:
    return LLMHealthResponse(
        status="ok" if _config_loaded else "starting",
        configLoaded=_config_loaded,
    )


@app.get(
    f"{_prefix()}/catalog/{{biz_key}}",
    response_model=LLMCatalogResponse,
    dependencies=[Depends(_authorize)],
)
async def catalog(biz_key: str, request: Request) -> LLMCatalogResponse:
    try:
        cfg = resolve_biz_config(biz_key)
        options = list_provider_options(biz_key)
    except Exception as exc:
        raise _http_error(request, exc, status_code=404, error_code="LLM_BIZ_NOT_FOUND") from exc
    return LLMCatalogResponse(
        bizKey=biz_key,
        kind=cfg.kind,
        defaultProviderKey=cfg.provider_key,
        options=[
            LLMProviderOptionResponse(
                providerKey=item.provider_key,
                backend=item.backend,
                model=item.model,
                contextWindow=item.context_window,
                inputModalities=list(item.input_modalities),
            )
            for item in options
        ],
    )


@app.post(
    f"{_prefix()}/chat",
    response_model=LLMChatResponse,
    dependencies=[Depends(_authorize)],
)
async def chat(body: LLMChatRequest, request: Request) -> LLMChatResponse:
    try:
        provider = _chat_provider(body.biz_key, body.provider_key, body.messages)
        result = await provider.chat(body.messages, tools=body.tools)
    except Exception as exc:
        raise _http_error(request, exc) from exc
    return LLMChatResponse.model_validate(response_to_wire(result))


@app.post(f"{_prefix()}/chat/stream", dependencies=[Depends(_authorize)])
async def chat_stream(body: LLMChatRequest, request: Request) -> StreamingResponse:
    try:
        provider = _chat_provider(body.biz_key, body.provider_key, body.messages)
    except Exception as exc:
        raise _http_error(request, exc) from exc

    async def events() -> AsyncIterator[str]:
        try:
            async for chunk in provider.chat_stream(body.messages, tools=body.tools):
                if await request.is_disconnected():
                    return
                yield _sse("chunk", chunk_to_wire(chunk))
            yield _sse("done", {})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("LLM stream failed request_id={}", request.state.request_id)
            yield _sse(
                "error",
                {
                    "errorCode": _error_code(exc),
                    "message": str(exc),
                    "requestId": request.state.request_id,
                },
            )

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post(
    f"{_prefix()}/embeddings",
    response_model=LLMEmbeddingResponse,
    dependencies=[Depends(_authorize)],
)
async def embeddings(body: LLMEmbeddingRequest, request: Request) -> LLMEmbeddingResponse:
    try:
        provider = _provider(body.biz_key, body.provider_key)
        vectors = await provider.embed(body.texts)
    except Exception as exc:
        raise _http_error(request, exc) from exc
    return LLMEmbeddingResponse(vectors=vectors)


@app.get(
    f"{_prefix()}/embeddings/dimension",
    response_model=LLMEmbeddingDimensionResponse,
    dependencies=[Depends(_authorize)],
)
async def embedding_dimension(
    request: Request,
    biz_key: str = Query(alias="bizKey"),
    provider_key: str | None = Query(default=None, alias="providerKey"),
) -> LLMEmbeddingDimensionResponse:
    try:
        provider = _provider(biz_key, provider_key)
        dimension = await provider.dimension()
    except Exception as exc:
        raise _http_error(request, exc) from exc
    return LLMEmbeddingDimensionResponse(dimension=dimension)


@app.post(
    f"{_prefix()}/rerank",
    response_model=LLMRerankResponse,
    dependencies=[Depends(_authorize)],
)
async def rerank(body: LLMRerankRequest, request: Request) -> LLMRerankResponse:
    try:
        provider = _provider(body.biz_key, body.provider_key)
        if isinstance(provider, DocumentScoreProvider):
            scores = await provider.score_documents(body.query, body.documents)
        else:
            scores = await score_documents_with_chat(provider, body.query, body.documents)
    except Exception as exc:
        raise _http_error(request, exc) from exc
    return LLMRerankResponse(
        scores=[
            LLMDocumentScoreResponse(
                score=score.clamped_score,
                reason=score.reason,
                debug=dict(score.debug),
            )
            for score in scores
        ]
    )


@app.get(
    f"{_prefix()}/speech/profile/{{biz_key}}",
    response_model=LLMSpeechProfileResponse,
    dependencies=[Depends(_authorize)],
)
async def speech_profile(biz_key: str, request: Request) -> LLMSpeechProfileResponse:
    try:
        cfg = get_biz_config(biz_key)
    except Exception as exc:
        raise _http_error(request, exc) from exc
    if cfg is None or cfg.kind != LLM_KIND_SPEECH:
        raise _http_error(
            request,
            ValueError(f"LLM speech biz config not found: {biz_key}"),
            status_code=404,
            error_code="LLM_SPEECH_BIZ_NOT_FOUND",
        )
    try:
        provider = LLMManager.get().get_speech_provider(biz_key)
    except Exception as exc:
        raise _http_error(request, exc) from exc
    profile = provider.profile
    return LLMSpeechProfileResponse(
        bizKey=biz_key,
        providerKey=profile.provider_key,
        model=profile.model,
        voice=profile.voice,
        responseFormat=profile.response_format,
        speed=profile.speed,
        cacheRevision=profile.cache_revision,
        configFingerprint=profile.config_fingerprint,
    )


@app.post(f"{_prefix()}/speech", dependencies=[Depends(_authorize)])
async def speech(body: LLMSpeechRequest, request: Request) -> Response:
    try:
        provider = LLMManager.get().get_speech_provider(
            body.biz_key,
            provider_key=body.provider_key,
        )
        payload = await provider.synthesize(body.text)
    except Exception as exc:
        raise _http_error(request, exc) from exc
    profile = provider.profile
    media_type = {
        "mp3": "audio/mpeg",
        "opus": "audio/ogg",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "wav": "audio/wav",
        "pcm": "audio/L16",
    }[profile.response_format]
    return Response(
        content=payload,
        media_type=media_type,
        headers={"X-Speech-Config-Fingerprint": profile.config_fingerprint},
    )


def _provider(biz_key: str, provider_key: str | None) -> LLMProvider:
    provider = LLMManager.get().get_provider(biz_key, provider_key=provider_key)
    if not isinstance(provider, LLMProvider):
        raise ValueError(f"LLM biz {biz_key!r} does not expose provider operations")
    return provider


def _chat_provider(
    biz_key: str,
    provider_key: str | None,
    messages: list[dict[str, object]],
) -> LLMProvider:
    cfg = resolve_biz_config(biz_key, provider_key=provider_key)
    if cfg.kind not in {"chat", "planner"}:
        raise ValueError(f"LLM biz {biz_key!r} does not support chat")
    required_modalities = _validate_chat_messages(messages)
    for modality in required_modalities:
        if modality not in cfg.input_modalities:
            raise LLMInputModalityUnsupportedError(modality, cfg.provider_key)
    return _provider(biz_key, provider_key)


def _validate_chat_messages(messages: list[dict[str, object]]) -> set[str]:
    required = {"text"}
    for message_index, message in enumerate(messages):
        content = message.get("content")
        if content is None or isinstance(content, str):
            continue
        if not isinstance(content, list):
            raise ValueError(f"messages[{message_index}].content must be a string or array")
        for part_index, part in enumerate(content):
            if not isinstance(part, dict):
                raise ValueError(
                    f"messages[{message_index}].content[{part_index}] must be an object"
                )
            part_type = str(part.get("type", "")).strip()
            if part_type == "text":
                if not isinstance(part.get("text"), str):
                    raise ValueError(
                        f"messages[{message_index}].content[{part_index}].text must be a string"
                    )
                continue
            if part_type != "image_url":
                raise ValueError(
                    f"messages[{message_index}].content[{part_index}].type is unsupported"
                )
            image_url = part.get("image_url")
            if not isinstance(image_url, dict) or not isinstance(image_url.get("url"), str):
                raise ValueError(
                    f"messages[{message_index}].content[{part_index}].image_url.url is required"
                )
            _validate_image_data_url(image_url["url"])
            required.add("image")
    return required


def _validate_image_data_url(value: str) -> None:
    prefix, separator, encoded = value.partition(",")
    if separator != "," or prefix not in {
        "data:image/png;base64",
        "data:image/jpeg;base64",
        "data:image/webp;base64",
    }:
        raise ValueError("image_url must be a PNG, JPEG, or WebP base64 data URL")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("image_url contains invalid base64 data") from exc
    signatures = {
        "data:image/png;base64": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
        "data:image/jpeg;base64": lambda data: data.startswith(b"\xff\xd8\xff"),
        "data:image/webp;base64": lambda data: (
            len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
        ),
    }
    if not signatures[prefix](payload):
        raise ValueError("image_url content does not match its declared image type")


def _validate_config() -> None:
    raw = load_llm_settings()
    biz = raw.get("biz")
    if not isinstance(biz, dict) or not biz:
        raise ValueError("llm_service/llm.yaml must define at least one biz route")
    for biz_key in biz:
        resolve_biz_config(str(biz_key))


def _http_error(
    request: Request,
    exc: Exception,
    *,
    status_code: int | None = None,
    error_code: str | None = None,
) -> HTTPException:
    if status_code is None:
        status_code = 422 if isinstance(exc, (ValueError, NotImplementedError)) else 502
    return HTTPException(
        status_code=status_code,
        detail={
            "errorCode": error_code or _error_code(exc),
            "message": str(exc),
            "requestId": request.state.request_id,
        },
    )


def _error_code(exc: Exception) -> str:
    if isinstance(exc, LLMInputModalityUnsupportedError):
        return "LLM_INPUT_MODALITY_UNSUPPORTED"
    if isinstance(exc, (ValueError, NotImplementedError)):
        return "LLM_REQUEST_INVALID"
    if isinstance(exc, TimeoutError):
        return "LLM_PROVIDER_TIMEOUT"
    return "LLM_PROVIDER_ERROR"


def _sse(event: str, payload: object) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
