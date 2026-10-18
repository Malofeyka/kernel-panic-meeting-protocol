# Агент: ИИ система для протоколирования совещаний Министерства

[![OpenSpec](https://img.shields.io/badge/Spec--Driven-OpenSpec-blue.svg)](openspec/)
[![Python](https://img.shields.io/badge/Python-3.11+-green.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-teal.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React%20%2B%20Tailwind-blue.svg)](frontend/)
[![Security](https://img.shields.io/badge/Security-Isolated%20On--Prem-red.svg)](#требования-информационной-безопасности)

Программно-аппаратный комплекс автоматизированного составления протоколов аппаратных и оперативных совещаний **Министерства образования Свердловской области** на основе аудиозаписей и сопроводительных материалов.

---

## 📌 О проекте

- **Дипломная тема:** Проект по теме *«Агент: ИИ система для протоколирования совещаний Министерства»*
- **Уровень сложности:** B
- **Тип работ:** Прикладной (практико-ориентированный)
- **Целевой заказчик и пользователи:** Секретариат Министерства образования Свердловской области
- **Ключевой результат:** Готовый проект протокола совещания в формате Microsoft Word (`.docx`) по утверждённому бланку с извлечением решений, поручений, сроков и ответственных лиц, подготовленный не позднее следующего дня после совещания.

---

## 👥 Состав команды и распределение ролей (5 человек)

| Роль | Зона ответственности | Ключевые задачи |
|---|---|---|
| **1. Team Lead / Архитектор системы** | Системная архитектура, OpenSpec, изоляция защищенного контура, координация команды и приёмка | [TL-101 .. TL-401](openspec/changes/001-initial-protocol-agent/tasks.md) |
| **2. AI / ML Engineer (Speech & LLM)** | Офлайн STT (аудио 1.5 ч), доменный словарь Минобразования, квантизация и инференс локальной российской LLM | [ML-101 .. ML-302](openspec/changes/001-initial-protocol-agent/tasks.md) |
| **3. Backend Engineer (NER, RAG, DOCX)** | Бизнес-логика на FastAPI, парсинг материалов, извлечение связок «Кто/Что/Срок», аналитика рисков, сборка DOCX | [BE-101 .. BE-301](openspec/changes/001-initial-protocol-agent/tasks.md) |
| **4. Frontend / Fullstack Developer** | Клиентский интерфейс React/Vite: загрузка файлов, интерактивный редактор проекта протокола, счетчик правок (до 2) | [FE-101 .. FE-301](openspec/changes/001-initial-protocol-agent/tasks.md) |
| **5. QA Engineer / AI Evaluator & TechWriter** | Оценка метрик качества LLM (Recall поручений, отсутствие галлюцинаций), разметка датасетов, инструкция пользователя | [QA-101 .. QA-401](openspec/changes/001-initial-protocol-agent/tasks.md) |

---

## 🔄 Схема бизнес-процесса

```mermaid
flowchart TD
    Start(["Начало: совещание завершено"]) --> Step1["Специалист вручную загружает аудиозапись и сопутствующие материалы"]
    Step1 --> Step2["ИИ-агент: транскрибация аудиозаписи (1–1.5 ч)"]
    Step2 --> Step3["ИИ-агент: извлечение решений, поручений, сроков, ответственных"]
    Step3 --> Step4["ИИ-агент: содержательная сверка с повесткой, шаблоном и прошлыми протоколами"]
    Step4 --> Step5["Формирование промежуточного проекта протокола"]
    Step5 --> Decision{"Специалист: проект корректен?"}
    
    Decision -- "Да" --> GenDocx["Формирование итогового Word-документа (.docx)"]
    Decision -- "Нет, нужны правки" --> Edit["Специалист вносит корректировки в визуальном редакторе"]
    
    Edit --> CheckCycles{"Кругов правок <= 2?"}
    CheckCycles -- "Да" --> ReGen["ИИ-агент: повторная генерация обновлённого варианта"]
    ReGen --> Decision
    
    CheckCycles -- "Нет (превышение)" --> Escalate["Эскалация: ручная точечная доработка специалистом"]
    Escalate --> GenDocx
    
    GenDocx --> Download["Специалист скачивает проект протокола (.docx)"]
    Download --> End(["Конец: проект протокола готов в течение дня после совещания"])
```

---

## 📁 Спецификации OpenSpec

Проект ведётся по методологии **Spec-Driven Development (OpenSpec)**:

- [`openspec/config.yaml`](openspec/config.yaml) — конфигурация проекта и правила спецификаций;
- **Базовые спецификации подсистем (`openspec/specs/`):**
  - [`transcription/spec.md`](openspec/specs/transcription/spec.md) — офлайн STT, обработка аудио 1–1.5 часа;
  - [`protocol-extraction/spec.md`](openspec/specs/protocol-extraction/spec.md) — извлечение поручений, сопоставление со списком участников, анализ пробелов и коллизий;
  - [`document-generation/spec.md`](openspec/specs/document-generation/spec.md) — формирование документа Word по утверждённому ведомственному бланку;
  - [`review-ui/spec.md`](openspec/specs/review-ui/spec.md) — визуальный редактор, лимит кругов правок ($\le 2$);
  - [`security-deployment/spec.md`](openspec/specs/security-deployment/spec.md) — требования автономности и изоляции контура.
- **Активный чейнджсет (`openspec/changes/001-initial-protocol-agent/`):**
  - [`proposal.md`](openspec/changes/001-initial-protocol-agent/proposal.md) — обоснование и границы продукта;
  - [`design.md`](openspec/changes/001-initial-protocol-agent/design.md) — техническая архитектура и структуры данных;
  - [`tasks.md`](openspec/changes/001-initial-protocol-agent/tasks.md) — матрица задач для 5 участников команды с критериями готовности (DoD).

---

## 📅 Дорожная карта и вехи

- **Октябрь – Ноябрь 2026:** Проектирование, подготовка датасета, PoC модулей STT и извлечения сущностей.
- **Декабрь 2026:** 🎯 **Тестовая версия (MVP)** — сквозной пайплайн «Аудио + материалы $\rightarrow$ Черновик $\rightarrow$ Редактор $\rightarrow$ DOCX».
- **Январь 2027:** Оптимизация скорости инференса на локальном ПК, минимизация галлюцинаций, доработка UX.
- **Февраль 2027:** 🎯 **Готовая версия (Release)** — приёмочные испытания, развёртывание на ПК в Министерстве, обучение секретариата.

---

## 🔒 Требования информационной безопасности
1. **Строгая автономность:** работа в изолированном контуре без передачи аудиозаписей, стенограмм и протоколов во внешние публичные облака.
2. **Отечественная технологическая база:** использование российской модели распознавания речи GigaAM и локального LLM-инференса (GigaChat On-Prem / Saiga / Vikhr).
3. **Размещение:** выделенное рабочее место (ПК) сотрудника Министерства образования Свердловской области.

---

## 🚀 Быстрый старт для разработчиков

### Бэкенд (с использованием `uv`)
```bash
# Установка зависимостей и создание виртуального окружения через uv
uv venv
source .venv/bin/activate
uv pip install -e .

# Либо запуск напрямую через uv run:
uv run uvicorn backend.app.main:app --reload --port 8000
```

### Локальные GigaAM и GigaChat
Для Windows нужен FFmpeg 8.1 shared. По умолчанию используется `C:\ffmpeg8\bin`; другой путь можно задать через `FFMPEG_BIN` в `.env`. Для первого скачивания VAD-модели `pyannote/segmentation-3.0` нужен `HF_TOKEN` с принятыми условиями доступа к модели.

GigaChat использует открытую модель `ai-sage/GigaChat3.1-10B-A1.8B-GGUF` (revision `97045b260251cfa86f5ad25638fa2dd074153446`, Q4_K_M, MIT). Вес сохраняется в `models/gigachat/GigaChat3.1-10B-A1.8B-q4_K_M.gguf`:

```bash
uv sync --extra dev
uv run python scripts/download_gigachat.py
```

Для инференса нужен [llama.cpp b11675](https://github.com/ggml-org/llama.cpp/releases/tag/b11675). Архивы `llama-b11675-bin-win-cuda-12.4-x64.zip` и `cudart-llama-bin-win-cuda-12.4-x64.zip` распаковываются в `tools/llama.cpp/`, где должен находиться `llama-server.exe`.

```powershell
# На 4 ГБ VRAM начинать без GPU offload; для коротких текстов ContextSize можно уменьшить до 4096
powershell -ExecutionPolicy Bypass -File scripts/start_gigachat.ps1 -ContextSize 40960 -GpuLayers 0
```

Контекст 40960 нужен для полного `test1.mp4`: его JSON-транскрибация содержит около 35,5 тыс. токенов. Для более длинных записей контекст подбирается отдельно; chunking пока не реализован. Обработка такого prompt на CPU занимает несколько минут, поэтому таймаут Python-клиента по умолчанию составляет 1800 секунд.

В другом терминале запускается связка STT → LLM:

```bash
uv run python test.py path/to/audio.mp4 --output data/transcription.json --summary-output data/summary.json --batch-size 4
```

Скрипт сохраняет транскрибацию GigaAM, передаёт её полный JSON (`model`, `source`, `text`, `segments`) в локальный GigaChat и сохраняет краткую суть в отдельный JSON. `GIGACHAT_BASE_URL` по умолчанию равен `http://127.0.0.1:8080`; разрешены только loopback-адреса. После скачивания обе модели работают без обращения к внешним API.

### API-якоря GigaChat для backend

- `GET /api/gigachat/health` — проверка готовности локального llama-server;
- `POST /api/gigachat/chat` — общий вызов модели:

  ```json
  {
    "prompt": "Кратко передай суть текста",
    "system_prompt": null,
    "temperature": 0.0,
    "max_tokens": 512
  }
  ```

  Ответ: `{"text": "..."}`.

- `POST /api/gigachat/summary` — принимает JSON транскрибации GigaAM и возвращает `{"summary": "..."}`.

### Фронтенд
```bash
cd frontend
npm install
npm run dev
```

---

## 🌿 Регламент работы с Git и ветками

В проекте действует строгое правило: **каждая новая задача из `tasks.md` разрабатывается в отдельной ветке**.  
Прямой коммит в ветку `main` запрещён. Слияние выполняется через Pull Request (PR) после успешного прохождения автоматических тестов (`uv run pytest`) и ревью.

### Шаблон именования веток:
```text
<тип>/<ID_ТАСКИ>[-краткое-описание]
```

#### Примеры:
- `feature/ML-101` или `feature/ML-101-offline-stt` — новая функциональность (STT, извлечение, генератор DOCX, UI-компоненты);
- `feature/BE-201-extract-action-items` — реализация пайплайна поручений;
- `feature/FE-201-review-editor` — визуальный редактор протокола;
- `fix/BE-102-docx-table-borders` — исправление бага в коде таски;
- `refactor/ML-301-stt-chunking` — оптимизация производительности или рефакторинг;
- `docs/QA-202-user-guide` — подготовка или обновление документации/инструкций.

### Формат сообщений коммитов (Conventional Commits):
```text
<тип>(<код-таски>): <краткое описание на русском или английском>
```
*Примеры:*
- `feat(ML-101): implement GigaAM chunked audio pipeline`
- `feat(BE-201): add action items and due dates extraction`
- `fix(BE-102): fix margins in official ministry docx template`

---

## 🛡️ Контроль качества (Quality Gates, CI & PR)

Перед слиянием любого кода в `main` в GitHub Actions CI автоматически запускается пайплайн проверки (`.github/workflows/ci.yml`):

1. **Линтинг и форматирование:**
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   ```
2. **Статическая типизация:**
   ```bash
   uv run mypy backend
   ```
3. **Покрытие тестами (Coverage Gate $\ge 80\%$):**
   ```bash
   uv run pytest --cov=backend --cov-fail-under=80
   ```
4. **Шаблон Pull Request:**
   При открытии PR автоматически применяется шаблон [`.github/pull_request_template.md`](.github/pull_request_template.md) с обязательным чек-листом соответствия OpenSpec, прохождения тестов и требований информационной безопасности.