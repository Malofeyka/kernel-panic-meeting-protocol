# Интеграция фронтенда с бэкендом

Документ для разработчика клиентской части (FE-101, FE-102, FE-201..FE-204). Полный контракт: [`openspec/specs/api/spec.md`](../../openspec/specs/api/spec.md), машиночитаемый — [`openapi.json`](openapi.json).

## 1. Запуск бэкенда для разработки фронта

Модели (GigaAM, GigaChat) для разработки UI не нужны: загружайте **готовую стенограмму** (`transcript_file`) вместо аудио. Для извлечения поручений всё равно нужен LLM-сервер; без него сессия переходит в `failed` с понятным текстом ошибки, и этот сценарий тоже нужно уметь показать.

```bash
uv run uvicorn backend.app.main:app --reload --port 8000
```

CORS по умолчанию разрешён для `http://localhost:5173` и `http://127.0.0.1:5173` (переменная `CORS_ORIGINS`). Надёжнее проксировать запросы через Vite:

```ts
// vite.config.ts
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
```

После `npm run build` бэкенд сам раздаёт `frontend/dist` по адресу `http://127.0.0.1:8000/`, поэтому на ПК Министерства работает один процесс.

## 2. Типы

Сгенерируйте типы из контракта, чтобы они не расходились с бэкендом:

```bash
npx openapi-typescript ../docs/api/openapi.json -o src/api/schema.d.ts
```

Краткая выжимка ключевых типов:

```ts
export type ProcessingStep =
  | "idle" | "uploading" | "transcribing" | "extracting"
  | "cross_checking" | "ready" | "refining" | "failed";

export type ActionItemStatus =
  | "valid" | "missing_date" | "missing_assignee" | "missing_assignee_and_date";

export interface ActionItem {
  id: string;
  task: string;
  assignee: string | null;        // «Фамилия И.О.» из списка участников или как прозвучало
  assignee_role: string | null;
  assignee_raw: string | null;    // как прозвучало в речи («Петрову»)
  due_date: string | null;        // ДД.ММ.ГГГГ
  due_date_raw: string | null;    // «до пятнадцатого ноября»
  is_recurring: boolean;          // «ежемесячно», «постоянно»
  status: ActionItemStatus;       // вычисляет сервер, клиент только отображает
  quote: string | null;           // цитата из стенограммы
  source_start: number | null;    // секунды — для подсветки в стенограмме
  source_end: number | null;
  origin: "ai" | "manual";
}

export interface Decision {
  id: string; text: string; quote: string | null;
  source_start: number | null; source_end: number | null; origin: "ai" | "manual";
}

export interface AgendaItem {
  item_number: number; topic: string; reporter: string | null;
  decisions: Decision[]; action_items: ActionItem[];
}

export interface Attendee { full_name: string; short_name: string; position: string | null }

export interface GapIssue {
  type: string; severity: "high" | "medium" | "low"; description: string;
  agenda_item_number: number | null; action_item_id: string | null;
  context_quote: string | null; source_start: number | null;
}
export interface Contradiction {
  id: string; scope: "meeting" | "archive"; description: string;
  action_item_ids: string[]; quotes: string[]; archive_reference: string | null;
}
export interface Risk {
  id: string; type: string; severity: "high" | "medium" | "low"; description: string;
  action_item_ids: string[]; archive_reference: string | null;
}

export interface ProtocolDraft {
  session_id: string;
  metadata: {
    meeting_title: string; meeting_date: string; protocol_number: string | null;
    chairperson: string | null; secretary: string | null; attendees: Attendee[];
  };
  agenda_items: AgendaItem[];
  analytics: { gaps: GapIssue[]; contradictions: Contradiction[]; risks: Risk[] };
  revision_cycle: { current_cycle: number; max_cycles: number; is_escalated_to_manual: boolean };
}
```

## 3. Сценарий экранов

### FE-101 — загрузка
```ts
const { session_id } = await post("/api/sessions/create", {
  meeting_title, meeting_date: "20.10.2026", protocol_number,
});
const form = new FormData();
form.append("audio_file", audio);                 // или form.append("transcript_file", file)
if (agenda) form.append("agenda_file", agenda);
if (attendees) form.append("attendees_file", attendees);
if (template) form.append("template_file", template);
archive.forEach((f) => form.append("archive_files", f));   // несколько файлов — одно имя поля
await fetch(`/api/sessions/${session_id}/upload`, { method: "POST", body: form });
```
Не выставляйте `Content-Type` вручную: браузер сам добавит boundary. Ошибки `400`/`413` содержат готовый текст в `detail`, его можно показывать пользователю как есть.

### Опрос статуса
```ts
async function waitUntilSettled(id: string, onTick: (s: StatusResponse) => void) {
  for (;;) {
    const s = await get<StatusResponse>(`/api/sessions/${id}/status`);
    onTick(s);                                   // progress_percent + current_step_description
    if (s.status === "ready" || s.status === "failed") return s;
    await new Promise((r) => setTimeout(r, 2500));
  }
}
```
- `failed` → показать `error_message` и кнопку «Повторить» (`POST /api/sessions/{id}/process`). Стенограмма кэшируется, поэтому повторного распознавания не будет;
- `ready` с непустым `error_message` (неудачная ИИ-правка) → показать предупреждение; проект при этом не изменился.

### FE-102 — восстановление после перезагрузки
Храните `session_id` в URL или `localStorage`. При открытии вызовите `GET /api/sessions/{id}`: `has_draft` означает, что можно открывать редактор, а `status` в процессе обработки — что нужно продолжить опрос. Список прошлых сессий отдаёт `GET /api/sessions`.

### FE-201/202 — редактор и аналитика
- Левая панель: `GET /transcript`. Клик по поручению прокручивает к сегменту, где `segment.start <= source_start`.
- Выпадающий список ответственных: `draft.metadata.attendees[].short_name`. Свободный ввод тоже допустим (подведомственная организация).
- Дата: формат `ДД.ММ.ГГГГ`. Неверный формат даст `422`.
- Подсветка проблем: `analytics.gaps[].action_item_id` и `contradictions/risks[].action_item_ids` указывают на `ActionItem.id`, а `agenda_item_number` — на вопрос.
- Сохранение: `POST /refine` с `{"action": "manual_save", "updated_agenda_items": draft.agenda_items, "updated_metadata": draft.metadata}`. В ответе приходит `updated_draft` с пересчитанными `status` и `analytics`, его нужно положить в стейт целиком.
- Для нового пункта, добавленного вручную, `id` можно не передавать (сервер сгенерирует), но поставьте `origin: "manual"`.

### FE-203 — круги правок
```ts
const r = await post(`/api/sessions/${id}/refine`, {
  action: "ai_regenerate",
  user_feedback,                         // обязательно, иначе 400
  updated_agenda_items: draft.agenda_items,  // несохранённые ручные правки
});
// r.status === "refining" → waitUntilSettled(), затем GET /draft
// r.revision_cycle: «Круг {current_cycle} из {max_cycles}»
```
- Кнопку «Обновить через ИИ» блокируйте при `is_escalated_to_manual === true`.
- `400` с текстом «Превышен лимит…» означает переход в режим ручной доработки. Правки из этого запроса сервер сохранил.
- Итог правки («что применено / что отклонено») приходит в `status.current_step_description`.

### FE-204 — экспорт
```ts
const e = await post(`/api/sessions/${id}/export`);
if (e.warnings.length) showWarnings(e.warnings);  // например, шаблон без полей
window.location.href = e.download_url;            // имя файла придёт в Content-Disposition
```
Любое сохранение правок сбрасывает экспорт, поэтому перед скачиванием всегда вызывайте `/export` заново.

## 4. Коды ответов

| Код | Когда | Что показать |
|---|---|---|
| `400` | неверный формат файла, нет аудио/стенограммы, пустой `user_feedback`, превышен лимит правок | `detail` |
| `404` | нет сессии, стенограмма или документ ещё не готовы | `detail` |
| `409` | сессия обрабатывается или проект ещё не сформирован | «Дождитесь завершения обработки» |
| `413` | файл больше `MAX_UPLOAD_MB` | `detail` |
| `422` | ошибка валидации (например, дата не `ДД.ММ.ГГГГ`) | поле из `detail[].loc` |
