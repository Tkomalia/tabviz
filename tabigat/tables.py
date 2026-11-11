"""Рендер ответа get-many в таблицу с фильтрами, сортировкой, пагинацией и экспортом."""
from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd
import streamlit as st

from . import config, crud_query, custom_fields, meta_cache
from .api import ApiClient, ApiError

_NO_VALUE_OPS = {"$isnull", "$notnull"}

# Реестры, записи которых можно править прямо на странице: путь → поля.
# Список точечный, а не «любое поле любого реестра»: правка вслепую по всем
# реестрам слишком легко портит данные, а PATCH здесь идёт в боевой API.
EDITABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "/api/v1/users/orgtree/orgtree": ("licensor_code",),
}

# JSON-поля, которые правятся как JSON целиком (см. _render_json_field_editor):
# путь → поля. signatures у Docs — ЭЦП документа с ссылками на PDF/CMS в MinIO;
# правка нужна, например, чтобы привязать signed_pdf_* к последней подписи,
# которую читает send-document (см. processes_el._render_signed_pdf_fix).
JSON_EDITABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "/api/v1/docs/main/docs": ("signatures",),
}

# Связи, которые подтягиваем вместе с реестром (crud `join`): путь → имена
# связей в ответе. Имена — свойства схемы из OpenAPI, не названия сущностей:
# у Users связь с персоной называется `person` (одна), у Persons связь с
# оргструктурой — `orgtree` (список). entity-meta имён связей не отдаёт
# (возвращает их без name), поэтому список задан явно.
RELATION_JOINS: dict[str, tuple[str, ...]] = {
    "/api/v1/users/main/users": ("person",),
    "/api/v1/users/persons/persons": ("orgtree",),
}

# поля, по которым подписываем связанную запись, в порядке предпочтения
_RELATION_NAME_FIELDS = ("full_name", "name", "username", "title", "email")


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


def _relation_label(item: Any) -> str:
    """Короткая подпись связанной записи: ФИО или наименование + ИИН/БИН.

    Связанные записи приходят целыми объектами, и в ячейке таблицы от них
    пользы нет (см. _flatten_cell — там был бы сырой JSON), поэтому в таблицу
    кладём подпись, а сам объект показываем в панели под таблицей."""
    if not isinstance(item, dict):
        return "" if item is None else str(item)

    fio = " ".join(
        str(item[field]).strip()
        for field in ("last_name", "first_name", "middle_name")
        if isinstance(item.get(field), str) and item[field].strip()
    )
    name = fio or next(
        (
            str(item[field]).strip() for field in _RELATION_NAME_FIELDS
            if isinstance(item.get(field), str) and item[field].strip()
        ),
        "",
    )
    code = item.get("iin") or item.get("bin")
    label = " ".join(part for part in (name, f"({code})" if code else "") if part)
    if label:
        return label
    return f"#{item['id']}" if item.get("id") is not None else ""


def _relation_items(value: Any) -> list[dict]:
    """Связь как список записей: `person` приходит объектом, `orgtree` — списком."""
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _relation_cell(value: Any) -> str:
    """Значение колонки связи: подписи через «; », для пустой связи — «—»."""
    items = _relation_items(value)
    if not items:
        return "—"
    labels = [label for label in map(_relation_label, items) if label]
    return "; ".join(labels) if labels else f"записей: {len(items)}"


def _render_relations(
    rows: list[dict], selected: list[int], joins: tuple[str, ...], state_key: str,
) -> None:
    """Связанные записи выбранной строки — полями, а не JSON в ячейке."""
    st.markdown("#### 🔗 Связанные записи")
    names = ", ".join(f"`{name}`" for name in joins)
    if not selected:
        st.caption(f"Выберите строку в таблице, чтобы увидеть {names}.")
        return

    row = rows[selected[0]]
    for join in joins:
        items = _relation_items(row.get(join))
        st.markdown(f"**`{join}`** — записей: {len(items)}")
        if not items:
            st.caption("Связанных записей нет.")
            continue
        st.dataframe(
            _to_dataframe(items), use_container_width=True, hide_index=True,
            key=f"{state_key}::rel::{join}",
        )


def _field_comment(fields: list[dict], name: str) -> str:
    """Описание поля из entity-meta — подпись понятнее голого имени колонки."""
    for field in fields:
        if field.get("name") == name:
            return field.get("comment") or ""
    return ""


def _row_title(row: dict) -> str:
    """Как назвать редактируемую запись: id + первое осмысленное имя."""
    parts = [f"#{row['id']}"] if row.get("id") is not None else []
    for field in ("name", "full_name", "title", "entity"):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
            break
    if row.get("bin"):
        parts.append(f"БИН {row['bin']}")
    return " · ".join(parts) or "запись"


def _render_row_editor(
    client: ApiClient, path: str, rows: list[dict], selected: list[int],
    editable: tuple[str, ...], fields: list[dict], state_key: str,
) -> None:
    """Правка разрешённых полей выбранной строки (PATCH записи целиком не
    трогаем — отправляем только изменённые поля, см. ApiClient.update)."""
    st.markdown("#### ✏️ Редактирование")
    names = ", ".join(f"`{name}`" for name in editable)
    if not selected:
        st.caption(f"Выберите строку в таблице, чтобы отредактировать {names}.")
        return

    row = rows[selected[0]]
    record_id = row.get("id")
    if record_id is None:
        st.warning("У записи нет `id` — обновить её нельзя.")
        return

    st.caption(f"Запись: **{_row_title(row)}**")
    values: dict[str, str] = {}
    for name in editable:
        key = f"{state_key}::edit::{record_id}::{name}"
        if key not in st.session_state:
            current = row.get(name)
            st.session_state[key] = "" if current is None else str(current)
        comment = _field_comment(fields, name)
        values[name] = st.text_input(
            f"{name} — {comment}" if comment else name, key=key,
        )

    changed = {
        name: (value.strip() or None)
        for name, value in values.items()
        if (value.strip() or None) != (row.get(name) or None)
    }
    if changed:
        st.caption(
            f"`PATCH {path}/{record_id}` · тело: "
            f"`{json.dumps(changed, ensure_ascii=False)}`"
        )
    else:
        st.caption("Значение не изменено.")

    save = st.button(
        "💾 Сохранить", type="primary", key=f"{state_key}::save::{record_id}",
        disabled=not changed, width="content",
    )
    if save and changed:
        try:
            with st.spinner("Сохранение..."):
                updated = client.update(path, record_id, changed)
        except ApiError as exc:
            st.error(str(exc))
            return
        # правим строку прямо в загруженном ответе — таблица покажет новое
        # значение без повторной загрузки всей страницы данных
        for name, value in changed.items():
            row[name] = updated.get(name, value) if isinstance(updated, dict) else value
        st.success("Запись обновлена.")
        st.rerun()


def _parse_json_value(value: Any) -> Any:
    """JSON-поле crud может вернуть объектом или JSON-строкой — приводим к объекту."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def _json_changes(old: Any, new: Any) -> list[str]:
    """Что поменялось между старым и новым значением — по ключам верхнего
    уровня (для signatures это отдельные подписи), внутри — по полям."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        return [] if old == new else ["значение заменено целиком"]
    changes = [f"удалён ключ `{key}`" for key in old if key not in new]
    changes += [f"добавлен ключ `{key}`" for key in new if key not in old]
    for key in new:
        if key not in old or old[key] == new[key]:
            continue
        before, after = old[key], new[key]
        if isinstance(before, dict) and isinstance(after, dict):
            fields = [f for f in (*before, *(f for f in after if f not in before))
                      if before.get(f) != after.get(f)]
            changes.append(f"`{key}`: поля {', '.join(f'`{f}`' for f in fields)}")
        else:
            changes.append(f"`{key}`: значение изменено")
    return changes


def _render_json_field_editor(
    client: ApiClient, path: str, rows: list[dict], selected: list[int],
    field: str, state_key: str,
) -> None:
    """Правка JSON-поля выбранной записи целиком (PATCH {field: <объект>}).

    Значение берётся свежим GET записи, а не из строки таблицы: поле могли
    не выбрать для загрузки, а с момента загрузки таблицы его могли поменять.
    Перед сохранением показывается, что именно изменится, и нужна галочка —
    PATCH идёт в боевой API."""
    st.markdown(f"#### 🧾 Редактирование `{field}`")
    if not selected:
        st.caption(f"Выберите строку в таблице, чтобы отредактировать `{field}`.")
        return

    row = rows[selected[0]]
    record_id = row.get("id")
    if record_id is None:
        st.warning("У записи нет `id` — обновить её нельзя.")
        return

    prefix = f"{state_key}::json::{field}::{record_id}"
    record_key, text_key = f"{prefix}::record", f"{prefix}::text"
    confirm_key, done_key = f"{prefix}::confirm", f"{prefix}::done"

    st.caption(f"Запись: **{_row_title(row)}**")
    if st.button("↻ Перечитать запись", key=f"{prefix}::reload", width="content"):
        for key in (record_key, text_key, confirm_key):
            st.session_state.pop(key, None)
    if record_key not in st.session_state:
        try:
            with st.spinner("Загрузка записи..."):
                st.session_state[record_key] = client.get_one(path, record_id)
        except ApiError as exc:
            st.error(str(exc))
            return
    record = st.session_state[record_key]
    if not isinstance(record, dict):
        st.warning("Неожиданный ответ на запрос записи.")
        return

    if st.session_state.pop(done_key, False):
        st.success(f"`{field}` сохранено, запись перечитана.")

    current = _parse_json_value(record.get(field))
    if text_key not in st.session_state:
        st.session_state[text_key] = json.dumps(current, ensure_ascii=False, indent=2)
    edited = st.text_area(f"{field} (JSON)", key=text_key, height=400)

    try:
        parsed = json.loads(edited)
    except (ValueError, TypeError) as exc:
        st.error(f"Невалидный JSON: {exc}")
        return
    if parsed is not None and not isinstance(parsed, dict):
        st.error("Ожидается JSON-объект (словарь) или null.")
        return

    changes = _json_changes(current, parsed)
    if not changes:
        st.caption("Значение не изменено.")
        return
    st.markdown(
        f"Будет изменено (`PATCH {path}/{record_id}` на `{client.base_url}`):\n"
        + "\n".join(f"- {change}" for change in changes)
    )

    confirm = st.checkbox("Подтверждаю запись в боевой API", key=confirm_key)
    save = st.button(
        "💾 Сохранить", type="primary", key=f"{prefix}::save",
        disabled=not confirm, width="content",
    )
    if not save:
        return
    try:
        with st.spinner("Сохранение..."):
            client.update(path, record_id, {field: parsed})
    except ApiError as exc:
        st.error(str(exc))
        return
    # перечитываем запись, чтобы в редакторе было то, что реально сохранилось
    row[field] = parsed
    for key in (record_key, text_key, confirm_key):
        st.session_state.pop(key, None)
    st.session_state[done_key] = True
    st.rerun()


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

    joins = RELATION_JOINS.get(path, ())

    # данные загружаем только по явному нажатию кнопки «Загрузить»
    if load:
        def _params(with_joins: tuple[str, ...]) -> dict:
            # fields не передаём — запрашиваем все доступные поля модели
            return crud_query.build_params(
                page=int(page), limit=int(limit),
                sort_field=None if sort_field.startswith("—") else sort_field,
                sort_dir=sort_dir,
                filters=filters,
                joins=list(with_joins) or None,
            )

        try:
            with st.spinner("Загрузка данных..."):
                result = client.get_many(path, _params(joins))
        except ApiError as exc:
            # связь может быть не разрешена на бэкенде — тогда ошибку даёт
            # именно join; реестр без связанных записей полезнее, чем ничего
            if not joins:
                st.error(str(exc))
                return
            st.warning(
                f"Связанные записи ({', '.join(joins)}) загрузить не удалось, "
                f"показываю реестр без них. Ошибка: {exc}"
            )
            joins = ()
            try:
                with st.spinner("Загрузка данных без связей..."):
                    result = client.get_many(path, _params(()))
            except ApiError as retry_exc:
                st.error(str(retry_exc))
                return
        st.session_state[state_key] = result

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

    # связанные записи — подписью вместо сырого JSON в ячейке
    loaded_joins = tuple(join for join in joins if join in df.columns)
    for join in loaded_joins:
        df[join] = [_relation_cell(row.get(join)) for row in rows]

    # показываем только выбранные колонки (из тех, что реально вернулись)
    cols = [c for c in display_fields if c in df.columns]
    view = df[cols] if cols else df

    editable = EDITABLE_FIELDS.get(path, ())
    json_editable = JSON_EDITABLE_FIELDS.get(path, ())
    if not editable and not json_editable and not loaded_joins:
        st.dataframe(view, use_container_width=True, hide_index=True)
        _export_buttons(view, entity)
        return

    # колонки связей и редактируемые поля добавляем принудительно: первых нет
    # в entity-meta (а значит и в выборе колонок), вторые иначе не покажут
    # результат правки, если колонку не выбрали для отображения
    extra = [
        c for c in (*loaded_joins, *editable)
        if c in df.columns and c not in view.columns
    ]
    if extra:
        view = df[[*view.columns, *extra]]

    event = st.dataframe(
        view, use_container_width=True, hide_index=True,
        selection_mode="single-row", on_select="rerun", key=f"{state_key}::table",
    )
    _export_buttons(view, entity)
    selected = [i for i in event.selection.rows if i < len(rows)]

    if loaded_joins:
        st.divider()
        _render_relations(rows, selected, loaded_joins, state_key)
    if editable:
        st.divider()
        _render_row_editor(client, path, rows, selected, editable, fields, state_key)
    for field in json_editable:
        st.divider()
        _render_json_field_editor(client, path, rows, selected, field, state_key)
