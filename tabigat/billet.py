"""Страница «Лесорубочный билет»: трёхуровневая drill-down таблица.

Уровни (каждый — get-many к известной модели с фильтрами):
  1. Лесовладельцы — orgtree, type_id=5, не удалённые.
  2. Лесничества   — orgtree, type_id=6, не удалённые, parent_id = id уровня 1.
  3. Выдела        — allocation-handbook, forestry_handbook_code = id уровня 2.
  4. Заявления     — logging-license-application, связанные с выбранным выделом.
  5. Расчётные поля — calculation-field, logging_license_application_id = id уровня 4.

Связь выдел↔заявление — many-to-many через pivot logging_license_application_allocation.
Вложенный фильтр allocation_handbook.id крашит crud (ambiguous "id"), поэтому уровень 4
получаем обратным join-ом: фильтруем сам выдел по его id и подгружаем join=logging_license_application.

`fields` сознательно НЕ передаём: entity-meta перечисляет в т.ч. невыбираемые поля
(на Laravel-бэке tab-forest выбор `archived_at` дёргает отсутствующий scope
`withArchived()`, а `is_overdue` — вычисляемое поле без столбца в БД). Поэтому
запрашиваем набор по умолчанию и показываем все вернувшиеся колонки.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from . import auth, config, crud_query, tables
from .api import ApiClient, ApiError

ORGTREE_PATH = "/api/v1/users/orgtree/orgtree"
ALLOCATION_HANDBOOK_PATH = "/api/v1/tab-forest/main/allocation-handbook"
CALCULATION_FIELD_PATH = "/api/v1/tab-forest/main/calculation-field"

# первыми в таблице показываем идентификатор и человекочитаемое имя
_PRIORITY_COLS = ("id", "name", "full_name", "full_name_ru", "code", "quarter",
                  "application_info_number", "status", "applicant")

# имя обратной связи на стороне allocation-handbook (belongsToMany)
_APPLICATIONS_JOIN = "logging_license_application"


def _load_level(client: ApiClient, path: str, filters: list[dict],
                limit: int) -> dict[str, Any] | None:
    params = crud_query.build_params(limit=limit, filters=filters)
    try:
        with st.spinner("Загрузка данных..."):
            return client.get_many(path, params)
    except ApiError as exc:
        st.error(str(exc))
        return None


def _order_columns(cols: list[str]) -> list[str]:
    head = [c for c in _PRIORITY_COLS if c in cols]
    tail = [c for c in cols if c not in head]
    return head + tail


def _load_applications(client: ApiClient, allocation_id: Any) -> list[dict] | None:
    """Заявления, связанные с выделом (обратный join через pivot).

    Фильтруем сам выдел по его id (надёжно) и подгружаем заявления join-ом —
    вложенный фильтр allocation_handbook.id крашит crud («ambiguous id»).
    """
    params = crud_query.build_params(
        limit=1, filters=[{"field": "id", "op": "$eq", "value": allocation_id}])
    params["join"] = _APPLICATIONS_JOIN
    try:
        with st.spinner("Загрузка заявлений..."):
            res = client.get_many(ALLOCATION_HANDBOOK_PATH, params)
    except ApiError as exc:
        st.error(str(exc))
        return None
    rows = res.get("data", [])
    if not rows:
        return []
    return rows[0].get(_APPLICATIONS_JOIN) or []


def _load_calculation_fields(client: ApiClient, application_id: Any,
                             limit: int) -> dict | None:
    """calculation-field, связанные с заявлением по FK logging_license_application_id."""
    return _load_level(
        client, CALCULATION_FIELD_PATH,
        filters=[{"field": "logging_license_application_id",
                  "op": "$eq", "value": application_id}],
        limit=limit,
    )


def _select_rows(rows: list[dict], key: str) -> dict | None:
    """Таблица с выбором одной строки; возвращает выбранную запись (или None)."""
    df = tables._to_dataframe(rows)
    df = df[_order_columns(list(df.columns))]
    event = st.dataframe(
        df, use_container_width=True, hide_index=True,
        selection_mode="single-row", on_select="rerun", key=key,
    )
    selected = event.selection.rows
    return rows[selected[0]] if selected else None


def _level_table(result: dict, key: str) -> dict | None:
    """Рисует уровень из ответа get-many с выбором строки; возвращает запись."""
    rows = result.get("data", [])
    total = result.get("total", len(rows))
    st.caption(f"Найдено: {total} (показано {len(rows)})")
    if not rows:
        st.info("Нет данных по заданным фильтрам.")
        return None
    return _select_rows(rows, key)


def render(client: ApiClient) -> None:
    st.title("🌲 Лесорубочный билет")
    auth.account_sidebar(client)

    with st.sidebar:
        st.markdown("### Параметры")
        limit = st.selectbox(
            "Записей на уровень", config.LIMIT_OPTIONS,
            index=config.LIMIT_OPTIONS.index(config.DEFAULT_LIMIT),
            key="billet::limit",
        )

    # --- Уровень 1: Лесовладельцы ---
    st.subheader("1. Лесовладельцы")
    res1 = _load_level(
        client, ORGTREE_PATH,
        filters=[
            {"field": "type_id", "op": "$eq", "value": 5},
            {"field": "deleted_at", "op": "$isnull", "value": ""},
        ],
        limit=int(limit),
    )
    if not res1:
        return
    sel1 = _level_table(res1, key="billet::l1")
    if not sel1:
        st.info("Выберите лесовладельца, чтобы увидеть лесничества.")
        return

    # --- Уровень 2: Лесничества (parent_id = id выбранного лесовладельца) ---
    st.subheader("2. Лесничества")
    res2 = _load_level(
        client, ORGTREE_PATH,
        filters=[
            {"field": "type_id", "op": "$eq", "value": 6},
            {"field": "deleted_at", "op": "$isnull", "value": ""},
            # parent — это relation; фильтруем по FK-столбцу parent_id
            # (по той же схеме, что type → type_id)
            {"field": "parent_id", "op": "$eq", "value": sel1["id"]},
        ],
        limit=int(limit),
    )
    if not res2:
        return
    sel2 = _level_table(res2, key=f"billet::l2::{sel1['id']}")
    if not sel2:
        st.info("Выберите лесничество, чтобы увидеть выдела.")
        return

    # --- Уровень 3: Выдела (forestry_handbook_code = id выбранного лесничества) ---
    st.subheader("3. Выдела")
    res3 = _load_level(
        client, ALLOCATION_HANDBOOK_PATH,
        filters=[
            {"field": "forestry_handbook_code", "op": "$eq", "value": sel2["id"]},
        ],
        limit=int(limit),
    )
    if not res3:
        return
    sel3 = _level_table(res3, key=f"billet::l3::{sel2['id']}")
    if not sel3:
        st.info("Выберите выдел, чтобы увидеть заявления (лесорубочные билеты).")
        return

    # --- Уровень 4: Заявления (logging-license-application) по выбранному выделу ---
    st.subheader("4. Заявления (лесорубочный билет)")
    apps = _load_applications(client, sel3["id"])
    if apps is None:
        return
    st.caption(f"Найдено: {len(apps)}")
    if not apps:
        st.info("По выбранному выделу заявлений нет.")
        return
    sel4 = _select_rows(apps, key=f"billet::l4::{sel3['id']}")
    if not sel4:
        st.info("Выберите заявление, чтобы увидеть расчётные поля.")
        return

    # --- Уровень 5: calculation-field по logging_license_application_id ---
    st.subheader("5. Расчётные поля (calculation-field)")
    res5 = _load_calculation_fields(client, sel4["id"], int(limit))
    if not res5:
        return
    _level_table(res5, key=f"billet::l5::{sel4['id']}")
