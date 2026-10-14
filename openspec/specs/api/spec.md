# Baseline Specification: REST API Contract

## Overview
Данный документ является единым официальным API-контрактом между клиентской частью (Web Frontend) и серверной частью (FastAPI Backend) программного комплекса «Агент: ИИ система для протоколирования совещаний Министерства образования».

Спецификация OpenAPI доступна динамически по пути: `/api/openapi.json` и интерактивно в `/docs` (Swagger UI).

---

## 1. Сводная таблица эндпоинтов

| Метод | Путь | Описание | Коды ответов |
|---|---|---|---|
| `GET` | `/api/health` | Проверка жизнеспособности сервиса и режима изоляции | `200` |
| `POST` | `/api/sessions/create` | Создание новой рабочей сессии протоколирования | `201` |
| `POST` | `/api/sessions/{id}/upload` | Пакетная загрузка аудио и сопутствующих файлов | `200`, `400`, `404` |
| `GET` | `/api/sessions/{id}/status` | Опрос прогресса обработки (STT $\rightarrow$ Extraction $\rightarrow$ Analytics) | `200`, `404` |
| `GET` | `/api/sessions/{id}/draft` | Получение структурированного проекта протокола и аналитики | `200`, `404` |
| `POST` | `/api/sessions/{id}/refine` | Внесение правок и запрос повторной генерации (до 2 циклов) | `200`, `400`, `404` |
| `POST` | `/api/sessions/{id}/export` | Формирование и ссылка на скачивание итогового `.docx` | `200`, `404` |

---

## 2. Детальное описание контрактов

### 2.1. `POST /api/sessions/create`
Создаёт контекст совещания.

* **Тело запроса (JSON, опционально):**
```json
{
  "meeting_title": "Аппаратное совещание Министерства образования",
  "meeting_date": "20.10.2026"
}
```
* **Ответ `201 Created`:**
```json
{
  "session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "status": "idle",
  "created_at": "2026-10-20T09:00:00Z"
}
```

---

### 2.2. `POST /api/sessions/{session_id}/upload`
Загрузка комплекта файлов совещания (формат `multipart/form-data`).

* **Параметры формы:**
  - `audio_file`: binary file (обязательно, форматы `.wav`, `.mp3`, `.m4a`)
  - `agenda_file`: binary file (опционально, `.docx`, `.pdf`, `.txt`)
  - `attendees_file`: binary file (опционально, список участников с должностями)
  - `template_file`: binary file (опционально, ведомственный шаблон `.docx`)
  - `archive_files`: array of binary files (опционально, прошлые протоколы)

* **Ответ `200 OK`:**
```json
{
  "session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "status": "transcribing",
  "progress_percent": 15,
  "current_step_description": "Файлы загружены. Запущена транскрибация аудиозаписи 'meeting_20_10.mp3'...",
  "updated_at": "2026-10-20T09:01:00Z"
}
```

---

### 2.3. `GET /api/sessions/{session_id}/status`
Опрос состояния выполнения конвейера обработки.

* **Значения поля `status`:**
  - `idle`: сессия создана, файлы не загружены
  - `transcribing`: распознавание речи (STT)
  - `extracting`: извлечение решений и поручений через российскую LLM
  - `cross_checking`: аналитика пробелов и сверка с архивом
  - `ready`: проект готов к вычитке секретарём
  - `refining`: выполняется повторная генерация правок
  - `failed`: ошибка обработки (заполняется `error_message`)

---

### 2.4. `GET /api/sessions/{session_id}/draft`
Возвращает текущий черновик протокола и отчёт аналитики.

* **Ответ `200 OK` (структура ProtocolDraft):**
```json
{
  "session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "metadata": {
    "meeting_title": "Аппаратное совещание",
    "meeting_date": "20.10.2026",
    "chairperson": "Министр образования Свердловской области",
    "secretary": "Петрова А.В.",
    "attendees": ["Иванов И.И.", "Сидоров С.С."]
  },
  "agenda_items": [
    {
      "item_number": 1,
      "topic": "О подготовке к проведению государственной итоговой аттестации",
      "reporter": "Иванов И.И.",
      "decisions": ["Принять информацию к сведению."],
      "action_items": [
        {
          "id": "act-1",
          "task": "Обеспечить готовность пунктов проведения экзаменов",
          "assignee": "Иванов И.И.",
          "assignee_role": "Начальник отдела контроля качества образования",
          "due_date": "15.11.2026",
          "status": "valid",
          "quote": "Иванову обеспечить готовность всех ППЭ до пятнадцатого ноября."
        }
      ]
    }
  ],
  "analytics": {
    "gaps": [
      {
        "type": "MISSING_DUE_DATE",
        "description": "Поручение по обновлению инструкций не содержит срока",
        "context_quote": "Также подготовьте обновленные инструкции для наблюдателей"
      }
    ],
    "contradictions": [],
    "risks": ["Срок сдачи ППЭ совпадает с началом проверок Рособрнадзора"]
  },
  "revision_cycle": {
    "current_cycle": 0,
    "max_cycles": 2,
    "is_escalated_to_manual": false
  }
}
```

---

### 2.5. `POST /api/sessions/{session_id}/refine`
Внесение правок секретарём. Поддерживает два режима:
1. `action: "ai_regenerate"` — запрос к ИИ на перегенерацию текста с учётом замечаний. Расходует лимит (не более 2 раз).
2. `action: "manual_save"` — сохранение точечных правок секретарём без расхода лимита генераций.

* **Тело запроса:**
```json
{
  "action": "ai_regenerate",
  "user_feedback": "Уточни срок по пункту 1.2 на 18 ноября, так как в стенограмме звучит уточнение от министра",
  "updated_metadata": null,
  "updated_agenda_items": null
}
```

* **Обработка ошибки лимита `400 Bad Request`:**
```json
{
  "detail": "Превышен лимит автоматических кругов правок (максимум 2). Переключено в режим ручной доработки."
}
```

---

### 2.6. `POST /api/sessions/{session_id}/export`
Генерация официального Word-файла протокола.

* **Ответ `200 OK`:**
```json
{
  "session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "file_name": "Протокол_совещания_9b1deb4d.docx",
  "download_url": "/api/sessions/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/download/Протокол_совещания_9b1deb4d.docx",
  "generated_at": "2026-10-20T10:15:00Z"
}
```
