"""Дисковый кэш полей сущностей (ответы entity-meta).

Чтобы не дёргать `{path}/entity-meta` при каждом открытии реестра, поля
сохраняются на диск в data/entity_meta_cache.json. Ключ верхнего уровня —
базовый URL клиента (среда), чтобы тест и прод не смешивались.

Структура файла:
    {
      "<base_url>": {
        "<path>": {"fetched_at": "<iso>", "fields": [ {entity-meta}, ... ]}
      }
    }
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from . import config
from .api import ApiClient


def load_cache() -> dict[str, Any]:
    """Читает кэш с диска. Возвращает {} если файла нет или он повреждён."""
    if not config.ENTITY_META_CACHE.exists():
        return {}
    try:
        with config.ENTITY_META_CACHE.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(cache: dict[str, Any]) -> None:
    """Пишет кэш на диск (создаёт каталог при отсутствии)."""
    config.ENTITY_META_CACHE.parent.mkdir(parents=True, exist_ok=True)
    config.ENTITY_META_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def cached_entry(client: ApiClient, path: str) -> dict[str, Any] | None:
    """Запись кэша {fetched_at, fields} для (среда, path) — только чтение, без сети."""
    return load_cache().get(client.base_url, {}).get(path)


def cached_fields(client: ApiClient, path: str) -> list[dict] | None:
    """Поля из кэша для (среда, path) — только чтение с диска, без сети."""
    entry = cached_entry(client, path)
    if entry and isinstance(entry.get("fields"), list):
        return entry["fields"]
    return None


def fetch_fields(client: ApiClient, path: str) -> list[dict]:
    """Запрашивает entity-meta, сохраняет в кэш и возвращает поля.

    Может бросить ApiError (пробрасывается из ApiClient.entity_meta).
    Используется как для первичного получения, так и для кнопки «Обновить».
    """
    fields = client.entity_meta(path)
    if not isinstance(fields, list):
        fields = []
    cache = load_cache()
    cache.setdefault(client.base_url, {})[path] = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "fields": fields,
    }
    save_cache(cache)
    return fields
