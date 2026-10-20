# Разметка ведомственного бланка протокола (docxtpl)

Генератор (`backend/app/services/docx_generator.py`) подставляет данные в шаблон Word через [docxtpl](https://docxtpl.readthedocs.io/) (синтаксис Jinja2). Если шаблон не загружен, не содержит полей `{{ … }}` или содержит ошибку, используется встроенный бланк (Times New Roman 14, поля 3/1,5/2/2 см), а пользователь получает предупреждение в `warnings`.

## Как разметить бланк Министерства

1. Откройте утверждённый бланк в Word.
2. Замените изменяемые значения полями из таблицы ниже. **Каждое поле набирайте целиком за один раз** и не меняйте форматирование внутри фигурных скобок, иначе Word разобьёт тег на несколько фрагментов и поле не сработает.
3. Циклы по абзацам задавайте отдельными абзацами `{%p for … %}` и `{%p endfor %}`, а по строкам таблицы — отдельными строками `{%tr for … %}` и `{%tr endfor %}` (первая ячейка строки).
4. Загрузите файл в поле «Шаблон протокола» и проверьте экспорт.

## Поля

| Поле | Пример |
|---|---|
| `{{ org_name }}` | Министерство образования Свердловской области (`ORGANIZATION_NAME`) |
| `{{ city }}` | г. Екатеринбург (`ORGANIZATION_CITY`) |
| `{{ meeting_title }}` | Аппаратное совещание |
| `{{ meeting_date }}` | 20.10.2026 |
| `{{ meeting_date_long }}` | 20 октября 2026 г. |
| `{{ protocol_number }}` | 12 (или `____`) |
| `{{ chairperson }}`, `{{ secretary }}` | Иванов И.И. (или `[уточнить]`) |
| `{{ attendees_text }}` | Иванов И.И., Петров П.П. |
| `attendees[]` | `a.name`, `a.full_name`, `a.position` |
| `agenda[]` | `item.number`, `item.topic`, `item.reporter`, `item.points[]` |
| `item.points[]` | `point.number` («1.2»), `point.text` (решение или поручение с исполнителем и сроком) |
| `actions[]` | `a.number`, `a.task`, `a.assignee`, `a.assignee_role`, `a.due` («до 15.11.2026» / «Ежемесячно» / `[уточнить]`) |

## Пример фрагмента

```
Присутствовали:
{%p for a in attendees %}
{{ a.name }}{% if a.position %} — {{ a.position }}{% endif %}
{%p endfor %}

{%p for item in agenda %}
{{ item.number }}. {{ item.topic }}
СЛУШАЛИ: {{ item.reporter }}
РЕШИЛИ:
{%p for point in item.points %}
{{ point.number }}. {{ point.text }}
{%p endfor %}
{%p endfor %}
```

Таблица поручений: строка заголовка, затем строка с `{%tr for a in actions %}`, затем строка `{{ a.number }} | {{ a.task }} | {{ a.assignee }} | {{ a.due }}`, затем строка с `{%tr endfor %}`.
