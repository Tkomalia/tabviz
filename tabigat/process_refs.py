"""Результаты поиска процесса по никаду: ref или отметка «не найден».

Поиск (issued-service-registry.application_info_number → process_id →
Processes.ref, см. processes_el._render_process_lookup) идёт в API и делается
только по явному клику, поэтому его результат запоминается: ref процесса не
меняется, второй раз спрашивать нечего. Благодаря этому найденный ref можно
показать колонкой в таблице никадов, в том числе после перезапуска приложения.

Хранится в data/nikad_process_refs.json — см. json_store. Сам процесс (с его
flow) здесь не хранится: он большой и нужен только в рамках сессии для сборки
тела запроса (лежит в st.session_state, см. processes_el._resend_body).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from . import json_store
from .config import DATA_DIR

FILE = DATA_DIR / "nikad_process_refs.json"

NOT_FOUND_LABEL = "не найден"


def load() -> dict[str, dict[str, Any]]:
    """{никад: {"found": bool, "ref", "process_id", "status", "at"}}."""
    return json_store.load(FILE)


def _remember(nikad: str, entry: dict[str, Any]) -> None:
    items = load()
    items[nikad] = {**entry, "at": dt.datetime.now().isoformat(timespec="seconds")}
    json_store.save(FILE, items)


def remember(nikad: str, process_id: Any, ref: Any, status: Any) -> None:
    """Запоминает найденный процесс."""
    _remember(nikad, {
        "found": True, "process_id": process_id, "ref": ref, "status": status,
    })


def remember_not_found(nikad: str) -> None:
    """Запоминает, что записи issued-service-registry с этим никадом нет.

    Ошибки запроса сюда не пишем — они говорят о недоступности API, а не об
    отсутствии процесса, и при следующей попытке результат может быть другим."""
    _remember(nikad, {"found": False})


def forget(nikad: str) -> None:
    items = load()
    if items.pop(nikad, None) is not None:
        json_store.save(FILE, items)


def ref_label(entry: dict[str, Any] | None) -> str:
    """Значение для колонки «Ref»: сам ref, отметка «не найден» или пусто,
    если поиск по этому никаду ещё не запускали."""
    if entry is None:
        return ""
    if not entry.get("found"):
        return NOT_FOUND_LABEL
    ref = entry.get("ref")
    return str(ref) if ref is not None else "—"
