"""Просмотр и редактирование записей issued-service-registry текущего процесса.

Находит записи реестра issued-service-registry, у которых process_id равен
id текущего процесса, показывает превью ключевых полей, затем позволяет
отредактировать result_issued_number и el_result_issued_nikad выбранной
записи и сохранить (PATCH).
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import crud_query
from .api import ApiClient, ApiError

PATH = "/api/v1/tab-forest/main/issued-service-registry"

_PREVIEW_COLS = (
    "id", "process_id", "doc_id", "application_info_number",
    "result_issued_number", "el_application_nikad", "el_result_issued_nikad",
)


def load_for_process(client: ApiClient, process_id: Any) -> list[dict] | None:
    """Записи issued-service-registry с этим process_id."""
    params = crud_query.build_params(
        limit=100, filters=[{"field": "process_id", "op": "$eq", "value": process_id}],
    )
    try:
        with st.spinner("Загрузка issued-service-registry..."):
            result = client.get_many(PATH, params)
    except ApiError as exc:
        st.error(str(exc))
        return None
    return result.get("data", [])


def load_for_nikad(client: ApiClient, nikad: str) -> list[dict] | None:
    """Записи issued-service-registry с этим application_info_number (никад
    заявления) — обратный поиск: никад → process_id."""
    params = crud_query.build_params(
        limit=100, filters=[{"field": "application_info_number", "op": "$eq", "value": nikad}],
    )
    try:
        with st.spinner("Поиск issued-service-registry..."):
            result = client.get_many(PATH, params)
    except ApiError as exc:
        st.error(str(exc))
        return None
    return result.get("data", [])


def _row_label(row: dict, index: int) -> str:
    rid = row.get("id")
    label = f"#{rid}" if rid is not None else f"[{index}]"
    number = row.get("application_info_number")
    if isinstance(number, str) and number.strip():
        label += f" — {number.strip()}"
    return label


def render(process_id: Any, state_key: str, client: ApiClient) -> None:
    """Панель issued-service-registry: превью + редактирование одной записи."""
    st.divider()
    st.markdown("### 📇 issued-service-registry процесса")

    if process_id is None:
        st.info("У процесса нет id.")
        return

    rows = load_for_process(client, process_id)
    if rows is None:
        return
    if not rows:
        st.info(f"Нет записей issued-service-registry с process_id = `{process_id}`.")
        return

    preview_df = pd.DataFrame(
        [{col: row.get(col) for col in _PREVIEW_COLS} for row in rows]
    )
    st.dataframe(preview_df, use_container_width=True, hide_index=True)

    options = [_row_label(row, i) for i, row in enumerate(rows)]
    choice = st.selectbox("Запись для редактирования", options, key=f"{state_key}::isr_pick")
    row = rows[options.index(choice)]
    record_id = row["id"]

    number_key = f"{state_key}::isr_number::{record_id}"
    nikad_key = f"{state_key}::isr_nikad::{record_id}"
    if number_key not in st.session_state:
        st.session_state[number_key] = row.get("result_issued_number") or ""
    if nikad_key not in st.session_state:
        st.session_state[nikad_key] = row.get("el_result_issued_nikad") or ""

    cols = st.columns(2)
    new_number = cols[0].text_input("result_issued_number", key=number_key)
    new_nikad = cols[1].text_input("el_result_issued_nikad", key=nikad_key)

    save = st.button(
        "💾 Сохранить", type="primary", key=f"{state_key}::isr_save::{record_id}",
    )
    if save:
        body = {
            "result_issued_number": new_number or None,
            "el_result_issued_nikad": new_nikad or None,
        }
        try:
            with st.spinner("Сохранение..."):
                updated = client.update(PATH, record_id, body)
        except ApiError as exc:
            st.error(str(exc))
        else:
            if isinstance(updated, dict):
                row["result_issued_number"] = updated.get("result_issued_number", new_number)
                row["el_result_issued_nikad"] = updated.get("el_result_issued_nikad", new_nikad)
            else:
                row["result_issued_number"] = new_number
                row["el_result_issued_nikad"] = new_nikad
            st.success("Запись обновлена.")
            st.rerun()
