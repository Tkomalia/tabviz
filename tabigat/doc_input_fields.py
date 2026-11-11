"""Просмотр и редактирование `input_fields` документов, связанных с процессом.

Процесс (реестр Processes) хранит связанные документы в поле `docs` —
списке UUID (может быть пустым). Для каждого id документ подгружается через
GET /api/v1/docs/main/docs/{id} (с кэшем в session_state), после чего можно
посмотреть и сохранить (PATCH) его input_fields.

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


def _fetch_docs(client: ApiClient, doc_ids: list[str], cache: dict) -> list[dict]:
    """Подгружает документы по id (с кэшем); документы с ошибкой загрузки
    пропускаются (ошибка выводится отдельным предупреждением)."""
    docs: list[dict] = []
    for doc_id in doc_ids:
        if doc_id not in cache:
            try:
                cache[doc_id] = client.get_one(DOCS_PATH, doc_id)
            except ApiError as exc:
                cache[doc_id] = exc
        entry = cache[doc_id]
        if isinstance(entry, ApiError):
            st.warning(f"Документ `{doc_id}` не загружен: {entry}")
            continue
        docs.append(entry)
    return docs


def _doc_label(doc: dict, index: int) -> str:
    doc_id = doc.get("id")
    label = f"#{doc_id}" if doc_id is not None else f"[{index}]"
    name = doc.get("name")
    if isinstance(name, str) and name.strip():
        label += f" — {name.strip()}"
    return label


def render(doc_ids: list[str], state_key: str, client: ApiClient) -> None:
    """Панель просмотра/редактирования input_fields документов процесса."""
    st.divider()
    st.markdown("### 📝 input_fields документов процесса")

    if not doc_ids:
        st.info("У процесса нет связанных документов (поле `docs` пусто).")
        return

    st.caption(
        "Документы из поля `docs` процесса — можно отредактировать `input_fields` "
        "как JSON и сохранить (`PATCH " + DOCS_PATH + "/{id}`)."
    )

    cache = st.session_state.setdefault(f"{state_key}::inputfieldsdoccache", {})
    with st.spinner("Загрузка документов..."):
        docs = _fetch_docs(client, doc_ids, cache)
    if not docs:
        st.info("Ни один документ не загрузился.")
        return

    candidates = [
        (doc, parsed)
        for doc in docs
        for parsed in (_parse_object(doc.get(_FIELD)),)
        if parsed is not None
    ]
    if not candidates:
        st.info("Ни у одного документа нет разбираемого input_fields.")
        return

    options = [_doc_label(doc, i) for i, (doc, _) in enumerate(candidates)]
    choice = st.selectbox("Документ", options, key=f"{state_key}::docpick")
    doc, parsed = candidates[options.index(choice)]
    doc_id = doc["id"]

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
            new_value = updated.get(_FIELD, parsed_edit) if isinstance(updated, dict) else parsed_edit
            doc[_FIELD] = new_value
            cache[doc_id] = doc
            st.success("input_fields обновлены.")
            st.rerun()
