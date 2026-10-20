import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.dependencies import get_services
from backend.app.api.gigachat import router as gigachat_router
from backend.app.api.routes import router as sessions_router
from backend.app.api.transcription import router as transcription_router

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Сессии, оборванные перезапуском сервера, не должны «висеть» в статусе обработки.
    get_services().store.recover_interrupted()
    yield


app = FastAPI(
    title="ИИ-система протоколирования совещаний Министерства образования",
    description="Автономный сервис генерации проектов протоколов в защищённом контуре",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(sessions_router)
app.include_router(transcription_router)
app.include_router(gigachat_router)


@app.get("/api/health", tags=["Служебные"])
async def health_check() -> dict[str, Any]:
    return {
        "status": "healthy",
        "service": "kernel-panic-meeting-protocol",
        "isolated_mode": True,
        "max_revision_cycles": get_services().settings.max_revision_cycles,
    }


# Собранный фронтенд (npm run build) раздаётся тем же сервером: один процесс на ПК.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
