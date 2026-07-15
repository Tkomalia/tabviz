"""Рендер ответа get-many в таблицу с фильтрами, сортировкой, пагинацией и экспортом."""
from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd
import streamlit as st

from . import config, crud_query, custom_fields, doc_input_fields, flow_breakdown, meta_cache
from .api import ApiClient, ApiError

_NO_VALUE_OPS = {"$isnull", "$notnull"}


def _flatten_cell(value: Any) -> Any:
    """Вложенные dict/list превращаем в компактный JSON, чтобы поместились в ячейку."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _to_dataframe(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.map(_flatten_cell)


def _export_buttons(df: pd.DataFrame, entity: str) -> None:
    if df.empty:
        return
    col_csv, col_xlsx = st.columns(2)
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    col_csv.download_button(
        "⬇️ CSV", csv_bytes, file_name=f"{entity}.csv", mime="text/csv",
        use_container_width=True,
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=entity[:31] or "data")
    col_xlsx.download_button(
        "⬇️ Excel", buf.getvalue(), file_name=f"{entity}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


def _with_id_field(fields: list[dict]) -> list[dict]:
    """Гарантируем наличие поля `id`.

    entity-meta для части реестров (processes, docs, tasks, …) не возвращает
    первичный ключ, но фильтровать/сортировать по нему нужно всегда — поэтому
    добавляем синтетическое поле `id` в начало списка, если его там нет.
    """
    if any(f.get("name") == "id" for f in fields):
        return fields
    id_field = {
        "name": "id",
        "type": "Number",
        "is_primary": True,
        "is_nullable": False,
        "is_relation": False,
        "comment": "ID",
    }
    return [id_field, *fields]


def _with_custom_fields(client: ApiClient, path: str, fields: list[dict]) -> list[dict]:
    """Добавляет пользовательские поля (см. custom_fields), которых нет в entity-meta."""
    existing = {f.get("name") for f in fields}
    extra = [
        {
            "name": name,
            "type": "—",
            "is_relation": False,
            "comment": "добавлено вручную",
            "custom": True,
        }
        for name in custom_fields.names(client.base_url, path)
        if name not in existing
    ]
    return [*fields, *extra]


def _custom_field_editor(client: ApiClient, path: str, state_key: str) -> None:
    """Сайдбар-блок: добавить/удалить своё поле для текущей модели."""
    current = custom_fields.names(client.base_url, path)
    title = "➕ Своё поле"
    if current:
        title += f" ({len(current)})"
    with st.expander(title):
        st.caption(
            "Поле, которого нет в entity-meta — чтобы фильтровать, "
            "сортировать и показывать его."
        )
        with st.form(key=f"{state_key}::addform", clear_on_submit=True):
            new = st.text_input(
                "Имя поля", placeholder="например, updated_at",
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Добавить", use_container_width=True)
        if submitted and new.strip():
            custom_fields.add(client.base_url, path, new)
            st.rerun()

        for name in current:
            cols = st.columns([5, 1])
            cols[0].caption(f"• `{name}`")
            if cols[1].button("✕", key=f"{state_key}::delfield::{name}",
                              help=f"Удалить «{name}»"):
                custom_fields.remove(client.base_url, path, name)
                st.rerun()


def _fields_meta_expander(fields: list[dict], entry: dict | None) -> None:
    """Справочный блок: список полей модели (name/type/comment/relation)."""
    fetched = (entry or {}).get("fetched_at")
    title = "📋 Поля модели"
    if fetched:
        title += f" (обновлено {fetched})"
    with st.expander(title):
        meta_df = pd.DataFrame(
            [
                {
                    "поле": f.get("name"),
                    "тип": f.get("type"),
                    "связь": "✓" if f.get("is_relation") else "",
                    "описание": f.get("comment"),
                }
                for f in fields
            ]
        )
        st.dataframe(meta_df, use_container_width=True, hide_index=True)


def _collect_filters(state_key: str, field_names: list[str]) -> list[dict]:
    """Несколько фильтров (AND): поле из списка + условие + значение."""
    st.markdown("#### Фильтры")
    filter_fields = st.multiselect(
        "Поля для фильтра", field_names, key=f"{state_key}::ffields",
    )
    filters: list[dict] = []
    for field in filter_fields:
        cols = st.columns([2, 3])
        op_label = cols[0].selectbox(
            "Условие", list(crud_query.FILTER_OPERATORS.keys()),
            key=f"{state_key}::fop::{field}", label_visibility="collapsed",
        )
        op = crud_query.FILTER_OPERATORS[op_label]
        value = ""
        if op not in _NO_VALUE_OPS:
            value = cols[1].text_input(
                f"Значение «{field}»", key=f"{state_key}::fval::{field}",
                placeholder=f"{field} {op_label}…", label_visibility="collapsed",
            )
        else:
            cols[1].caption(f"{field}: {op_label}")
        filters.append({"field": field, "op": op, "value": value})
    return filters


def render_registry(client: ApiClient, registry: dict) -> None:
    """Отрисовывает один реестр: поля (entity-meta) → выбор полей/фильтров → get-many."""
    path = registry["path"]
    entity = registry["entity"]
    state_key = f"reg::{path}"

    st.subheader(registry.get("summary") or entity)
    st.caption(f"`GET {path}`")

    # --- поля модели: с диска (без сети); запрос только по кнопке ---
    fields = meta_cache.cached_fields(client, path)
    if fields is None:
        st.info("Поля модели ещё не загружены.")
        if st.button("📥 Получить поля (entity-meta)", type="primary",
                     key=f"{state_key}::getmeta"):
            try:
                with st.spinner("Запрос entity-meta..."):
                    meta_cache.fetch_fields(client, path)
                st.rerun()
            except ApiError as exc:
                st.error(str(exc))
        return

    fields = _with_id_field(fields)
    fields = _with_custom_fields(client, path, fields)
    entry = meta_cache.cached_entry(client, path)
    field_names = [f.get("name") for f in fields if f.get("name")]
    # по умолчанию показываем все скалярные поля (relation требуют join — исключаем)
    default_cols = [f["name"] for f in fields
                    if f.get("name") and not f.get("is_relation")]

    _fields_meta_expander(fields, entry)

    # --- контролы выборки в сайдбаре ---
    with st.sidebar:
        st.divider()
        st.markdown("### Параметры выборки")

        if st.button("🔄 Обновить поля (entity-meta)", use_container_width=True,
                     key=f"{state_key}::refreshmeta"):
            try:
                with st.spinner("Обновление полей..."):
                    meta_cache.fetch_fields(client, path)
                st.rerun()
            except ApiError as exc:
                st.error(str(exc))

        _custom_field_editor(client, path, state_key)

        display_fields = st.multiselect(
            "Поля для отображения", field_names, default=default_cols,
            key=f"{state_key}::dfields",
            help="Фильтр отображаемых колонок. Запрос всегда тянет все поля; "
                 "здесь выбираются только показываемые столбцы.",
        )

        limit = st.selectbox(
            "Записей на странице", config.LIMIT_OPTIONS,
            index=config.LIMIT_OPTIONS.index(config.DEFAULT_LIMIT),
            key=f"{state_key}::limit",
        )
        page = st.number_input("Страница", min_value=1, value=1, step=1,
                               key=f"{state_key}::page")

        st.markdown("#### Сортировка")
        sort_field = st.selectbox(
            "Поле сортировки", ["— без сортировки —"] + field_names,
            key=f"{state_key}::sfield",
        )
        sort_dir = st.radio("Направление", ["ASC", "DESC"], horizontal=True,
                            key=f"{state_key}::sdir")

        filters = _collect_filters(state_key, field_names)

        load = st.button("🔄 Загрузить", type="primary", use_container_width=True,
                         key=f"{state_key}::load")

    # данные загружаем только по явному нажатию кнопки «Загрузить»
    if load:
        # fields не передаём — запрашиваем все доступные поля модели
        params = crud_query.build_params(
            page=int(page), limit=int(limit),
            sort_field=None if sort_field.startswith("—") else sort_field,
            sort_dir=sort_dir,
            filters=filters,
        )
        try:
            with st.spinner("Загрузка данных..."):
                result = client.get_many(path, params)
            st.session_state[state_key] = result
        except ApiError as exc:
            st.error(str(exc))
            return

    result = st.session_state.get(state_key)
    if not result:
        st.info("Выберите поля и фильтры в левой панели и нажмите «🔄 Загрузить».")
        return

    rows = result.get("data", [])
    total = result.get("total", len(rows))
    df = _to_dataframe(rows)

    st.markdown(
        f"**Всего записей:** {total} &nbsp;|&nbsp; "
        f"страница {result.get('page', '?')} из {result.get('pageCount', '?')} &nbsp;|&nbsp; "
        f"на странице: {len(rows)}"
    )

    if df.empty:
        st.info("Нет данных по заданным параметрам.")
        return

    # показываем только выбранные колонки (из тех, что реально вернулись)
    cols = [c for c in display_fields if c in df.columns]
    view = df[cols] if cols else df

    st.dataframe(view, use_container_width=True, hide_index=True)
    _export_buttons(view, entity)

    # разбор поля flow (реестр Processes) — панель под таблицей
    flow_breakdown.render(rows, state_key, client)

    # просмотр/редактирование input_fields (реестр Docs) — панель под таблицей
    doc_input_fields.render(rows, state_key, client, path)
