"""Просмотр и редактирование поля `input_fields` реестра Docs.

Аналогично flow_breakdown для Processes: панель появляется под таблицей
автоматически, если в загруженных строках есть разбираемое поле input_fields.
В отличие от flow_breakdown, редактирование мутирует данные на бэкенде,
поэтому дополнительно привязано к конкретному пути реестра (DOCS_PATH) —
иначе PATCH мог бы улететь не туда для реестров с похожим по имени полем
(например doc-templates тоже имеет input_fields).

У input_fields нет задокументированной схемы (маппинга UUID→имя поля),
поэтому редактируется как plain JSON.
"""
from __future__ import annotations

import json
from typing import Any

import streamlit as st

from .api import ApiClient, ApiError

DOCS_PATH = "/api/v1/docs/main/docs"
_FIELD = "input_fields"


def _parse_object(value: Any) -> dict | None:
    """Приводит input_fields к dict (crud может вернуть dict или JSON-строку)."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    return value if isinstance(value, dict) else None


def _row_label(row: dict, index: int) -> str:
    rid = row.get("id")
    label = f"#{rid}" if rid is not None else f"[{index}]"
    name = row.get("name")
    if isinstance(name, str) and name.strip():
        label += f" — {name.strip()}"
    return label


def render(rows: list[dict], state_key: str, client: ApiClient, path: str) -> None:
    """Панель просмотра/редактирования input_fields; активна только для реестра Docs."""
    if path != DOCS_PATH:
        return

    candidates = [
        (row, parsed)
        for row in rows
        if row.get("id") is not None
        for parsed in (_parse_object(row.get(_FIELD)),)
        if parsed is not None
    ]
    if not candidates:
        return

    st.divider()
    st.markdown("### 📝 input_fields документа")
    st.caption(
        "Содержимое `input_fields` выбранной записи — можно отредактировать "
        "как JSON и сохранить (`PATCH " + DOCS_PATH + "/{id}`)."
    )

    options = [_row_label(row, i) for i, (row, _) in enumerate(candidates)]
    choice = st.selectbox("Документ", options, key=f"{state_key}::docpick")
    row, parsed = candidates[options.index(choice)]
    doc_id = row["id"]

    text_key = f"{state_key}::inputfields::{doc_id}"
    if text_key not in st.session_state:
        st.session_state[text_key] = json.dumps(parsed, ensure_ascii=False, indent=2)

    edited = st.text_area("input_fields (JSON)", key=text_key, height=400)

    error: str | None = None
    parsed_edit: dict | None = None
    try:
        parsed_edit = json.loads(edited)
    except (ValueError, TypeError) as exc:
        error = f"Невалидный JSON: {exc}"
    else:
        if not isinstance(parsed_edit, dict):
            parsed_edit = None
            error = "Ожидается JSON-объект (словарь), а не список/строка/число."

    if error:
        st.error(error)

    save = st.button(
        "💾 Сохранить", type="primary", key=f"{state_key}::savefields::{doc_id}",
        disabled=error is not None,
    )
    if save and parsed_edit is not None:
        try:
            with st.spinner("Сохранение..."):
                updated = client.update(DOCS_PATH, doc_id, {_FIELD: parsed_edit})
        except ApiError as exc:
            st.error(str(exc))
        else:
            row[_FIELD] = updated.get(_FIELD, parsed_edit) if isinstance(updated, dict) else parsed_edit
            st.success("input_fields обновлены.")
            st.rerun()
