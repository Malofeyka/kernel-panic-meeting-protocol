from pydantic import BaseModel, Field


class GigaChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Пользовательский запрос к локальной LLM")
    system_prompt: str | None = Field(None, description="Необязательная системная инструкция")
    temperature: float = Field(0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(512, ge=1, le=4096)


class GigaChatResponse(BaseModel):
    text: str = Field(..., description="Ответ локальной LLM")


class GigaChatSummaryResponse(BaseModel):
    summary: str = Field(..., description="Краткая суть стенограммы совещания")


class GigaChatHealthResponse(BaseModel):
    status: str = Field(..., description="Статус локального сервера GigaChat")
