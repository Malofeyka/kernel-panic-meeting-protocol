from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.gigachat import (
    GigaChatHealthResponse,
    GigaChatRequest,
    GigaChatResponse,
    GigaChatSummaryResponse,
)
from backend.app.schemas.transcription import MeetingTranscription
from backend.app.services.gigachat_client import (
    GigaChatClient,
    GigaChatError,
    GigaChatUnavailableError,
)

router = APIRouter(prefix="/api/gigachat", tags=["GigaChat (локальная LLM)"])
_client: GigaChatClient | None = None


def _get_client() -> GigaChatClient:
    global _client
    if _client is None:
        load_dotenv()
        _client = GigaChatClient()
    return _client


def _as_http_exception(exc: GigaChatError) -> HTTPException:
    status_code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if isinstance(exc, GigaChatUnavailableError)
        else status.HTTP_502_BAD_GATEWAY
    )
    return HTTPException(status_code=status_code, detail=str(exc))


@router.get("/health", response_model=GigaChatHealthResponse, summary="Статус локального GigaChat")
def gigachat_health() -> GigaChatHealthResponse:
    try:
        _get_client().health()
    except GigaChatError as exc:
        raise _as_http_exception(exc) from exc
    return GigaChatHealthResponse(status="ok")


@router.post("/chat", response_model=GigaChatResponse, summary="Запрос к локальному GigaChat")
def gigachat_chat(request: GigaChatRequest) -> GigaChatResponse:
    try:
        text = _get_client().chat(
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except GigaChatError as exc:
        raise _as_http_exception(exc) from exc
    return GigaChatResponse(text=text)


@router.post(
    "/summary",
    response_model=GigaChatSummaryResponse,
    summary="Краткая суть JSON-транскрибации GigaAM",
)
def gigachat_summary(transcription: MeetingTranscription) -> GigaChatSummaryResponse:
    try:
        summary = _get_client().summarize(transcription)
    except GigaChatError as exc:
        raise _as_http_exception(exc) from exc
    return GigaChatSummaryResponse(summary=summary)
