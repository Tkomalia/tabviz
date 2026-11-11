"""Страница «Интеграция с ЕЛ»: разбор flow и документов одного процесса по ref.

Показывает конкретный процесс (реестр Processes), найденный по номеру `ref`:
  - разбор его flow — типы узлов, действия service_task, microservice_call
    по topic, сборка body/query для конкретного вызова (см. flow_breakdown);
  - просмотр/редактирование input_fields документов, связанных с процессом
    через поле `docs` (список UUID) — см. doc_input_fields;
  - просмотр/редактирование записей issued-service-registry с process_id,
    равным id процесса — см. issued_service_registry.

Аналог billet.py, но вместо многоуровневого drill-down — один процесс,
найденный по ref.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from . import auth, crud_query, doc_input_fields, flow_breakdown, issued_service_registry
from .api import ApiClient, ApiError

PROCESSES_PATH = "/api/v1/processes/main/processes"
_STATE_KEY = "el::process"


def _load_process_by_ref(client: ApiClient, ref: int) -> dict[str, Any] | None:
    params = crud_query.build_params(
        limit=1, filters=[{"field": "ref", "op": "$eq", "value": ref}],
    )
    try:
        with st.spinner("Загрузка процесса..."):
            result = client.get_many(PROCESSES_PATH, params)
    except ApiError as exc:
        st.error(str(exc))
        return None
    rows = result.get("data", [])
    return rows[0] if rows else None


def render(client: ApiClient) -> None:
    st.title("🔗 Интеграция с ЕЛ")
    auth.account_sidebar(client)

    with st.sidebar:
        st.markdown("### Параметры")
        ref = st.number_input("Ref процесса", min_value=1, value=1, step=1, key="el::ref")
        load = st.button(
            "🔄 Загрузить", type="primary", use_container_width=True, key="el::load",
        )

    if load:
        row = _load_process_by_ref(client, int(ref))
        if row is None:
            st.warning(f"Процесс с ref={int(ref)} не найден.")
            st.session_state.pop(_STATE_KEY, None)
        else:
            st.session_state[_STATE_KEY] = row

    row = st.session_state.get(_STATE_KEY)
    if not row:
        st.info("Укажите ref процесса в левой панели и нажмите «🔄 Загрузить».")
        return

    st.caption(
        f"Процесс `#{row.get('id', '?')}` · ref `{row.get('ref', '?')}` · "
        f"статус `{row.get('status', '—')}`"
    )

    state_key = f"el::{row.get('ref')}"
    flow_breakdown.render([row], state_key, client, show_picker=False)
    doc_input_fields.render(row.get("docs") or [], state_key, client)
    issued_service_registry.render(row.get("id"), state_key, client)
