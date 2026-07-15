"""Каталог реестров: чтение data/registries.json и группировка по доменам."""
from __future__ import annotations

import json
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def load_catalog() -> list[dict]:
    if not config.REGISTRIES_FILE.exists():
        raise FileNotFoundError(
            "Не найден data/registries.json. Запустите: python scripts/fetch_openapi.py"
        )
    with config.REGISTRIES_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


def domains() -> list[str]:
    """Список доменов, в которых есть реестры (отсортирован по RU-названию)."""
    seen = {r["domain"] for r in load_catalog()}
    return sorted(seen, key=config.domain_label)


def registries_in(domain: str) -> list[dict]:
    items = [r for r in load_catalog() if r["domain"] == domain]
    items.sort(key=lambda r: r["entity"])
    return items
