"""Пользовательские поля моделей.

entity-meta возвращает не все колонки сущности (служебные поля, вложенные
связи и т.п. могут не приходить). Чтобы можно было фильтровать/сортировать/
показывать такие поля, пользователь добавляет их вручную. Список хранится на
диске по (среда, path), как и кэш entity-meta.

Структура файла data/custom_fields.json:
    {
      "<base_url>": {
        "<path>": ["field_a", "field_b"]
      }
    }
"""
from __future__ import annotations

import json
from typing import Any

from . import config


def _load() -> dict[str, Any]:
    """Читает файл с диска. Возвращает {} если файла нет или он повреждён."""
    if not config.CUSTOM_FIELDS_FILE.exists():
        return {}
    try:
        with config.CUSTOM_FIELDS_FILE.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, Any]) -> None:
    config.CUSTOM_FIELDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.CUSTOM_FIELDS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def names(base_url: str, path: str) -> list[str]:
    """Имена пользовательских полей для (среда, path)."""
    got = _load().get(base_url, {}).get(path, [])
    return [n for n in got if isinstance(n, str) and n] if isinstance(got, list) else []


def add(base_url: str, path: str, name: str) -> None:
    """Добавляет поле (без дублей). Пустые имена игнорируются."""
    name = name.strip()
    if not name:
        return
    data = _load()
    lst = data.setdefault(base_url, {}).setdefault(path, [])
    if name not in lst:
        lst.append(name)
        _save(data)


def remove(base_url: str, path: str, name: str) -> None:
    """Удаляет поле, если оно есть."""
    data = _load()
    lst = data.get(base_url, {}).get(path)
    if isinstance(lst, list) and name in lst:
        lst.remove(name)
        _save(data)
