"""Сборка query-параметров под @nestjsx/crud."""
from __future__ import annotations

from typing import Any

# Операторы фильтра crud, удобные для UI
FILTER_OPERATORS: dict[str, str] = {
    "содержит": "$cont",
    "равно": "$eq",
    "не равно": "$ne",
    "больше": "$gt",
    "больше или равно": "$gte",
    "меньше": "$lt",
    "меньше или равно": "$lte",
    "начинается с": "$starts",
    "пусто": "$isnull",
    "не пусто": "$notnull",
}

_NO_VALUE_OPS = {"$isnull", "$notnull"}


def build_params(
    *,
    page: int = 1,
    limit: int = 50,
    sort_field: str | None = None,
    sort_dir: str = "ASC",
    search: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Формирует dict query-параметров для get_many.

    filters: список {"field": str, "op": "$cont", "value": Any}
    """
    params: dict[str, Any] = {"page": page, "limit": limit}

    if sort_field:
        params["sort"] = f"{sort_field},{sort_dir}"

    if fields:
        params["fields"] = ",".join(fields)

    # `s` — полнотекстовый поиск по всем полям не поддерживается crud напрямую;
    # для простого поиска используем filter ||$cont|| по выбранному полю в UI.
    if search:
        # глобальный поиск через `s` с $or не строим — оставляем явные фильтры
        pass

    filter_list: list[str] = []
    for f in filters or []:
        field = f.get("field")
        op = f.get("op", "$cont")
        if not field:
            continue
        if op in _NO_VALUE_OPS:
            filter_list.append(f"{field}||{op}")
        else:
            value = f.get("value", "")
            if value == "" or value is None:
                continue
            filter_list.append(f"{field}||{op}||{value}")

    if filter_list:
        # requests сериализует список как повторяющиеся ключи filter=...&filter=...
        params["filter"] = filter_list

    return params
