#!/usr/bin/env python3
"""
Заглушка локального GigaChat (llama-server, OpenAI-совместимый API на :8080) для разработки
фронтенда с настоящим бэкендом без модели.

Извлечение рассчитано на тестовое совещание из make-test-data.py: решения и поручения
находятся по ключевым фразам стенограммы. ИИ-правка дописывает срок и исполнителя
из текста замечания в первое неполное поручение.

    python3 scripts/fake-llm.py
"""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SEG = re.compile(r"^\[(\d+)\s*\|[^\]]*\]\s*(.*)$", re.MULTILINE)

# (вопрос, ключ для поиска сегмента, задача, исполнитель, срок)
ACTIONS = [
    (
        1,
        "Иванову обеспечить",
        "Обеспечить готовность всех пунктов проведения экзаменов",
        "Иванову",
        "до пятнадцатого ноября",
    ),
    (
        1,
        "подготовьте обновлённые инструкции",
        "Подготовить обновлённые инструкции для наблюдателей",
        "Сергей Сергеевич",
        None,
    ),
    (
        2,
        "договориться о переносе",
        "Согласовать с подрядчиками перенос сроков по трём объектам",
        None,
        "до двадцатого",
    ),
    (
        2,
        "к первому декабря",
        "Представить сводку о ходе работ по каждому объекту",
        "Дмитрий Андреевич",
        "к первому декабря",
    ),
]
DECISIONS = [
    (1, "Информацию принимаем к сведению", "Принять информацию к сведению"),
    (2, "признаём удовлетворительной", "Признать работу по графику ремонта удовлетворительной"),
    (2, "вернёмся к этому вопросу", "Рассмотреть вопрос повторно на совещании в декабре"),
]


def extraction(prompt: str) -> dict:
    segs = {int(i): t for i, t in SEG.findall(prompt)}

    def find(key: str):
        for i, t in segs.items():
            if key.lower() in t.lower():
                return i, t
        return None

    out = {"decisions": [], "action_items": [], "reports": []}
    for item, key, text in DECISIONS:
        if hit := find(key):
            out["decisions"].append(
                {
                    "agenda_item": item,
                    "topic": None,
                    "text": text,
                    "quote": hit[1],
                    "segment_ids": [hit[0]],
                }
            )
    for item, key, task, who, due in ACTIONS:
        if hit := find(key):
            out["action_items"].append(
                {
                    "agenda_item": item,
                    "topic": None,
                    "task": task,
                    "assignee_mention": who,
                    "due_date_mention": due,
                    "quote": hit[1],
                    "segment_ids": [hit[0]],
                }
            )
    if find("слово Игорю Ивановичу"):
        out["reports"].append({"agenda_item": 1, "reporter_mention": "Игорю Ивановичу Иванову"})
    if find("Дмитрий Андреевич, пожалуйста"):
        out["reports"].append({"agenda_item": 2, "reporter_mention": "Дмитрий Андреевич"})
    return out


def refine(prompt: str) -> dict:
    feedback = prompt.rsplit("Замечание секретаря:", 1)[-1]
    ops = []
    # Первое поручение, где чего-то не хватает
    for m in re.finditer(
        r"\[(act-[0-9a-f]+)\][^\n]*Ответственный: ([^|]+)\| Срок: ([^\n]+)", prompt
    ):
        act, who, due = m.group(1), m.group(2).strip(), m.group(3).strip()
        if who != "не указан" and due != "не указан":
            continue
        op = {
            "op": "update_action_item",
            "target_id": act,
            "agenda_item": None,
            "text": None,
            "assignee_mention": None,
            "due_date_mention": None,
            "quote": None,
            "segment_ids": [],
        }
        if d := re.search(r"(?:до|к)\s+\d{1,2}[.\s]\S+", feedback):
            op["due_date_mention"] = d.group(0)
        if w := re.search(r"\b([А-ЯЁ][а-яё]+(?:ов|ев|ин|ова|ева|ина|ой|ому|у|а))\b", feedback):
            op["assignee_mention"] = w.group(1)
        if op["due_date_mention"] or op["assignee_mention"]:
            ops.append(op)
            break
    return {"operations": ops}


class H(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, {"status": "ok"})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["content-length"])))
        prompt = req["messages"][-1]["content"]
        schema = json.dumps(req.get("response_format", {}))
        body = refine(prompt) if '"operations"' in schema else extraction(prompt)
        self._send(
            200, {"choices": [{"message": {"content": json.dumps(body, ensure_ascii=False)}}]}
        )

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", 8080), H).serve_forever()
