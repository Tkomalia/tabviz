"""Отложенные никады страницы «Процессы с ЕЛ»: локальная пометка с примечанием.

Пометка ничего не меняет в статусах топиков — они выводятся из файлов и из
последовательности топиков (см. processes_el._kind_status и
_apply_success_implication). Это отдельный слой «этот никад разобран, вот
почему его пока не трогаем», чтобы такие записи можно было убрать из списка,
не подменяя фактическую картину.

Хранится в data/deferred_nikads.json — см. json_store (там же о том, почему
локальный файл, а не session_state или сервер).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from . import json_store
from .config import DATA_DIR

FILE = DATA_DIR / "deferred_nikads.json"


def load() -> dict[str, dict[str, Any]]:
    """{никад: {"note": примечание, "at": когда отложен}}."""
    return json_store.load(FILE)


def _save(items: dict[str, dict[str, Any]]) -> None:
    json_store.save(FILE, items)


def defer(nikad: str, note: str) -> None:
    """Откладывает никад (или обновляет примечание уже отложенного)."""
    items = load()
    items[nikad] = {
        "note": note.strip(),
        "at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    _save(items)


def undefer(nikad: str) -> None:
    """Снимает пометку; если её не было — ничего не делает."""
    items = load()
    if items.pop(nikad, None) is not None:
        _save(items)


def note_of(entry: dict[str, Any] | None) -> str:
    """Примечание записи или пустая строка (примечание необязательно)."""
    note = (entry or {}).get("note")
    return note.strip() if isinstance(note, str) else ""
