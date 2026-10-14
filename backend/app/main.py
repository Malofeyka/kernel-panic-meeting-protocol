from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.routes import router as sessions_router

app = FastAPI(
    title="ИИ-система протоколирования совещаний Министерства образования",
    description="Автономный сервис генерации проектов протоколов в защищённом контуре",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router)


@app.get("/api/health", tags=["Служебные"])
async def health_check():
    return {
        "status": "healthy",
        "service": "kernel-panic-meeting-protocol",
        "isolated_mode": True,
        "max_revision_cycles": 2,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
