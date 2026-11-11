"""Маленькие локальные JSON-справочники вида «никад → запись» (в data/).

Общая часть для deferrals (отложенные никады с примечанием) и process_refs
(найденные ref процессов): такие пометки негде держать на сервере, а
st.session_state не выживает перезапуск приложения. Папка data/ не под гитом
(см. config.DATA_DIR).

Файлы читаются при каждом обращении — они маленькие, зато правки руками
подхватываются сразу, без сброса кэшей.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, dict[str, Any]]:
    """{ключ: запись-словарь} из файла.

    Отсутствующий или испорченный файл — это просто пустой справочник:
    пометки вспомогательные, из-за них страница падать не должна. Записи
    неожидаемого типа отбрасываются по той же причине."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): entry for key, entry in raw.items() if isinstance(entry, dict)}


def save(path: Path, items: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
