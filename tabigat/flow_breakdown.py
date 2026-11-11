"""Панель разбора поля `flow` (реестр Processes) по типам узлов и действий.

Три уровня вложенности:
  1. Узлы flow          — группировка по `nodes[].type`.
  2. service_task        — группировка по `nodes[].actions[].type`.
  3. microservice_call   — группировка по `nodes[].actions[].data.service_topic`.

Панель появляется под таблицей автоматически, если в загруженных строках есть
разбираемое поле `flow` со списком `nodes` (т.е. фактически только для Processes).
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

import pandas as pd
import streamlit as st

from . import xml_files
from .api import ApiClient, ApiError

# поле реестра Processes, в котором лежит граф процесса
_FLOW_FIELD = "flow"
# кандидаты на человекочитаемое имя процесса для подписи в селекторе
_NAME_FIELDS = ("name", "title", "process_name", "template_name", "entity")
# куда идём за документом для ссылок type=doc (см. _resolve_doc_ref)
_DOCS_PATH = "/api/v1/docs/main/docs"

# топики elicense, для которых можно проверить тестовые файлы (см.
# _render_test_files_check): search_field — поле в собранном body с искомым
# никадом, file_pattern — общая часть имени файлов запрос/ответ этого топика
# (файлы вида <timestamp>_<file_pattern>_request.xml / _response.xml).
TOPIC_FILE_ACTIONS: dict[str, dict[str, str]] = {
    "send_demand": {"search_field": "nikad", "file_pattern": "demand"},
    "get_document_nikad": {"search_field": "number", "file_pattern": "nikad_document"},
    "send_document": {"search_field": "request_identification_number", "file_pattern": "pdf"},
}

# REST-эндпоинты, соответствующие этим топикам elicense — поля собранного body
# совпадают с DTO этих эндпоинтов один в один, поэтому его можно отправлять
# напрямую (после правок пользователя) — см. _render_call_section.
# Публичная — переиспользуется страницей processes_el.py для переотправки.
TOPIC_CALL_PATHS: dict[str, str] = {
    "send_demand": "/api/v1/integrations/elicense/send-demand",
    "get_document_nikad": "/api/v1/integrations/elicense/get-document-nikad",
    "send_document": "/api/v1/integrations/elicense/send-document",
}


def _parse_flow(value: Any) -> dict | None:
    """Приводит значение поля flow к dict (crud может вернуть dict или JSON-строку)."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    if isinstance(value, dict) and isinstance(value.get("nodes"), list):
        return value
    return None


def _flows_with_rows(rows: list[dict]) -> list[tuple[dict, dict]]:
    """Пары (строка-процесс, распарсенный flow) для строк с разбираемым flow."""
    out: list[tuple[dict, dict]] = []
    for row in rows:
        flow = _parse_flow(row.get(_FLOW_FIELD))
        if flow is not None:
            out.append((row, flow))
    return out


def _process_label(row: dict, index: int) -> str:
    """Подпись процесса в селекторе: id + первое доступное имя."""
    parts: list[str] = []
    rid = row.get("id")
    parts.append(f"#{rid}" if rid is not None else f"[{index}]")
    for field in _NAME_FIELDS:
        val = row.get(field)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
            break
    return " — ".join(parts)


def analyze(flows: list[dict]) -> dict[str, Counter]:
    """Считает три разбивки по списку flow (можно передать один или несколько).

    Возвращает счётчики:
      node_types      — все узлы по `type`;
      action_types    — действия узлов service_task по `type`;
      service_topics  — действия microservice_call по `data.service_topic`.
    """
    node_types: Counter = Counter()
    action_types: Counter = Counter()
    service_topics: Counter = Counter()

    for flow in flows:
        for node in flow.get("nodes") or []:
            ntype = node.get("type") or "—"
            node_types[ntype] += 1
            if ntype != "service_task":
                continue
            for action in node.get("actions") or []:
                atype = action.get("type") or "—"
                action_types[atype] += 1
                if atype == "microservice_call":
                    topic = (action.get("data") or {}).get("service_topic") or "—"
                    service_topics[topic] += 1

    return {
        "node_types": node_types,
        "action_types": action_types,
        "service_topics": service_topics,
    }


def nodes_for_topic(flows: list[dict], topic: str) -> list[dict]:
    """Узлы service_task, содержащие microservice_call с данным service_topic.

    Узел добавляется один раз, даже если у него несколько таких действий.
    """
    out: list[dict] = []
    for flow in flows:
        for node in flow.get("nodes") or []:
            if node.get("type") != "service_task":
                continue
            for action in node.get("actions") or []:
                if action.get("type") != "microservice_call":
                    continue
                if (action.get("data") or {}).get("service_topic") == topic:
                    out.append(node)
                    break
    return out


# --- сборка body/query microservice_call ------------------------------------
# значения в body/query — либо литералы, либо ссылки {key, type, child}:
#   node         → результат другого узла (можно резолвить из payload);
#   doc          → поле документа (значения в flow нет — только маркер);
#   current_date → текущая дата.
_MISSING = object()


def _index_nodes(flow: dict) -> dict[str, dict]:
    """{id узла: узел} для одного flow. Резолвим строго в пределах своего flow —
    id узлов повторяются между процессами одного шаблона."""
    return {n["id"]: n for n in flow.get("nodes") or [] if n.get("id")}


def _short(val: Any, n: int = 8) -> str:
    s = str(val)
    return f"{s[:n]}…" if len(s) > n + 1 else s


def _child_path(child: Any) -> list[str]:
    """Цепочку вложенных child превращаем в список ключей пути."""
    path: list[str] = []
    cur = child
    while isinstance(cur, dict):
        key = cur.get("key")
        if key is not None:
            path.append(str(key))
        cur = cur.get("child")
    return path


def _is_ref(value: Any) -> bool:
    return isinstance(value, dict) and "key" in value and "type" in value


def _resolve_node_ref(node: dict, path: list[str]) -> tuple[Any, bool]:
    """Идёт по payload каждого действия узла вдоль path; (значение, найдено?)."""
    for action in node.get("actions") or []:
        cur: Any = action.get("payload")
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                cur = _MISSING
                break
        if cur is not _MISSING:
            return cur, True
    return None, False


def _created_doc_id(node: dict) -> str | None:
    """id созданного документа из payload узла, создавшего документ:

    - create_doc         → payload.result.created_doc_id
    - create_service_doc → payload.result.doc_id
    """
    for action in node.get("actions") or []:
        result = (action.get("payload") or {}).get("result") or {}
        atype = action.get("type")
        if atype == "create_doc":
            doc_id = result.get("created_doc_id")
        elif atype == "create_service_doc":
            doc_id = result.get("doc_id")
        else:
            continue
        if doc_id:
            return doc_id
    return None


def _fetch_doc(client: ApiClient, doc_cache: dict, doc_id: str) -> Any:
    """GET /docs/main/docs/{doc_id} с кэшем в doc_cache (значение или ApiError)."""
    if doc_id not in doc_cache:
        try:
            doc_cache[doc_id] = client.get_one(_DOCS_PATH, doc_id)
        except ApiError as exc:
            doc_cache[doc_id] = exc
    return doc_cache[doc_id]


def _dig(doc: dict, path: list[str]) -> tuple[Any, bool]:
    """Спускается по вложенным полям документа вдоль path.

    Первый элемент path — имя поля на документе (input_fields/doc_meta_data),
    остальные — ключи внутри его содержимого; содержимое может быть JSON-строкой."""
    cur: Any = doc
    for key in path:
        if isinstance(cur, str):
            try:
                cur = json.loads(cur)
            except (ValueError, TypeError):
                return None, False
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None, False
    return cur, True


def _resolve_doc_ref(
    key: str, path: list[str], nodes_by_id: dict[str, dict],
    client: ApiClient | None, doc_cache: dict,
) -> Any:
    """Ссылка type=doc: узел(create_doc) → created_doc_id → GET docs → поле по path.

    Возвращает None, если узел/документ/поле не найдены или значение — null;
    assemble в этом случае показывает исходную (нерезолвленную) ссылку.
    Ошибку запроса к API оставляем видимой."""
    node = nodes_by_id.get(key)
    if node is None:
        return None
    doc_id = _created_doc_id(node)
    if doc_id is None:
        return None
    if client is None:
        return None
    doc = _fetch_doc(client, doc_cache, doc_id)
    if isinstance(doc, ApiError):
        return f"<doc {_short(doc_id)} — ошибка загрузки: {doc}>"
    value, ok = _dig(doc, path)
    return value if ok else None


def _resolve_ref(
    ref: dict, nodes_by_id: dict[str, dict],
    client: ApiClient | None = None, doc_cache: dict | None = None,
) -> Any:
    """Ссылку заменяем на реальное значение (node/doc) или маркер (current_date).

    Возвращает None, если узел не найден, ещё не выполнен или значение — null;
    assemble в этом случае показывает исходную (нерезолвленную) ссылку."""
    rtype = ref.get("type")
    key = ref.get("key")
    path = _child_path(ref.get("child"))
    if rtype == "current_date":
        return "<current_date>"
    if rtype == "doc":
        return _resolve_doc_ref(
            key, path, nodes_by_id, client,
            doc_cache if doc_cache is not None else {},
        )
    if rtype == "node":
        node = nodes_by_id.get(key)
        if node is None:
            return None
        value, ok = _resolve_node_ref(node, path)
        return value if ok else None
    return f"<{rtype}>"


def assemble(
    obj: Any, nodes_by_id: dict[str, dict],
    client: ApiClient | None = None, doc_cache: dict | None = None,
) -> dict | None:
    """Собирает body/query: ссылки заменяет на значения, литералы оставляет.

    Если ссылку не удалось резолвить (узел/документ/поле не найдены) или её
    значение — null, поле всё равно остаётся в результате, но со своим
    исходным (нерезолвленным) значением — как было в шаблоне body/query.
    Возвращает None только для не-dict/пустого body (например [])."""
    if not isinstance(obj, dict) or not obj:
        return None
    result = {}
    for field, value in obj.items():
        if _is_ref(value):
            resolved = _resolve_ref(value, nodes_by_id, client, doc_cache)
            result[field] = resolved if resolved is not None else value
        else:
            result[field] = value
    return result


def body_for_topic(
    process: dict, action_name: str, client: ApiClient, doc_cache: dict | None = None,
) -> dict | None:
    """Собранный body первого microservice_call с этим топиком во flow процесса.

    То же, что показывает вкладка «Сборка body/query» (см. _render_body_assembly),
    но без UI — для страниц, которым нужно готовое тело запроса по топику
    (см. processes_el._resend_body). action_name сравнивается с последним
    сегментом service_topic. Ходит в API за документами (ссылки type=doc),
    поэтому вызывать только по явному действию пользователя."""
    flow = _parse_flow(process.get(_FLOW_FIELD))
    if flow is None:
        return None
    for _node, action, idx in _iter_microservice_calls(flow):
        data = action.get("data") or {}
        if (data.get("service_topic") or "").rsplit(".", 1)[-1] == action_name:
            return assemble(
                data.get("body"), idx, client,
                doc_cache if doc_cache is not None else {},
            )
    return None


def _iter_microservice_calls(flow: dict):
    """(узел, действие, индекс flow) для всех microservice_call узлов service_task одного flow."""
    idx = _index_nodes(flow)
    for node in flow.get("nodes") or []:
        if node.get("type") != "service_task":
            continue
        for action in node.get("actions") or []:
            if action.get("type") != "microservice_call":
                continue
            yield node, action, idx


def _microservice_calls(
    flows: list[dict], topic: str | None
) -> list[tuple[dict, dict, dict[str, dict]]]:
    """(узел, действие microservice_call, индекс родного flow); topic=None — без фильтра."""
    out: list[tuple[dict, dict, dict[str, dict]]] = []
    for flow in flows:
        for node, action, idx in _iter_microservice_calls(flow):
            if topic is not None and (action.get("data") or {}).get("service_topic") != topic:
                continue
            out.append((node, action, idx))
    return out


def _counter_df(counter: Counter, label: str) -> pd.DataFrame:
    """Счётчик → DataFrame с колонками [label, количество, доля], сортировка по убыванию."""
    total = sum(counter.values()) or 1
    rows = [
        {label: key, "количество": cnt, "доля": cnt / total}
        for key, cnt in counter.most_common()
    ]
    return pd.DataFrame(rows)


def _render_section(counter: Counter, label: str, empty_msg: str) -> None:
    """Секция разбивки: горизонтальная гистограмма + таблица с долями."""
    if not counter:
        st.info(empty_msg)
        return
    df = _counter_df(counter, label)
    chart_col, table_col = st.columns([2, 3])
    with chart_col:
        st.bar_chart(df, x=label, y="количество", horizontal=True)
    with table_col:
        st.dataframe(
            df, use_container_width=True, hide_index=True,
            column_config={
                "количество": st.column_config.NumberColumn("Кол-во"),
                "доля": st.column_config.ProgressColumn(
                    "Доля", format="%.0f%%", min_value=0.0, max_value=1.0,
                ),
            },
        )


def matched_test_files(files: list[str], pattern: str) -> list[str]:
    """Из списка имён файлов находит request-файлы данного типа (pattern —
    kind из xml_files.parse_filename, точное сравнение — иначе, например,
    'nikad_demand_request.xml' ложно матчится под pattern='demand', т.к. оба
    оканчиваются на '_demand_request.xml') и для каждого добавляет производное
    имя response-файла. Порядок: request, response, request, response, ..."""
    result: list[str] = []
    for f in files:
        parsed = xml_files.parse_filename(f)
        if parsed == (pattern, "request"):
            result.append(f)
            result.append(xml_files.response_filename(f))
    return result


def _render_test_files_check(
    client: ApiClient, topic: str | None, body: dict | None, state_key: str,
) -> None:
    """Кнопка «Проверить запросы»: ищет тестовые файлы elicense по никаду из
    body и показывает содержимое найденных пар request/response."""
    action_name = (topic or "").rsplit(".", 1)[-1]
    conf = TOPIC_FILE_ACTIONS.get(action_name)
    if conf is None:
        return

    search_field, pattern = conf["search_field"], conf["file_pattern"]
    text = (body or {}).get(search_field)
    if not isinstance(text, str) or not text.strip():
        st.caption(
            f"Для проверки запросов нужно строковое значение поля `{search_field}` "
            "в собранном body (сейчас недоступно)."
        )
        return

    st.markdown("**Тестовые файлы elicense:**")
    result_key = f"{state_key}::testfiles::{action_name}::{text}"
    check = st.button("🔎 Проверить запросы", key=f"{state_key}::checkfiles::{action_name}")
    if check:
        try:
            with st.spinner(f"Поиск файлов по «{text}»..."):
                resp = client.search_test_files(text)
        except ApiError as exc:
            st.error(str(exc))
        else:
            files = resp.get("data") if isinstance(resp, dict) else None
            st.session_state[result_key] = matched_test_files(files or [], pattern)

    matched = st.session_state.get(result_key)
    if matched is None:
        return
    if not matched:
        st.info(f"Файлы с текстом «{text}» не найдены.")
        return

    st.caption(f"Найдено файлов: {len(matched)}")
    for i, filename in enumerate(matched):
        with st.expander(filename, expanded=(i == 0)):
            content_key = f"elfilecontent::{filename}"
            if content_key not in st.session_state:
                try:
                    with st.spinner("Загрузка содержимого..."):
                        st.session_state[content_key] = client.download_test_file(filename)
                except ApiError as exc:
                    st.session_state[content_key] = f"[Ошибка загрузки: {exc}]"
            st.code(st.session_state[content_key], language="xml", wrap_lines=True)


def _render_call_section(
    client: ApiClient, action_name: str, body: dict | None,
    state_key: str, call_id: str,
) -> None:
    """Позволяет скорректировать собранный body и повторно вызвать REST-метод,
    соответствующий данному топику elicense (см. TOPIC_CALL_PATHS)."""
    path = TOPIC_CALL_PATHS.get(action_name)
    if path is None:
        return

    st.markdown("**Повторный вызов метода:**")
    st.caption(f"`POST {path}`")

    text_key = f"{state_key}::callbody::{call_id}"
    if text_key not in st.session_state:
        st.session_state[text_key] = json.dumps(body or {}, ensure_ascii=False, indent=2)

    edited = st.text_area(
        "Тело запроса (можно скорректировать перед вызовом)",
        key=text_key, height=300,
    )

    error: str | None = None
    parsed_body: dict | None = None
    try:
        parsed_body = json.loads(edited)
    except (ValueError, TypeError) as exc:
        error = f"Невалидный JSON: {exc}"
    else:
        if not isinstance(parsed_body, dict):
            parsed_body = None
            error = "Ожидается JSON-объект (словарь)."

    if error:
        st.error(error)

    call = st.button(
        "🚀 Вызвать метод", type="primary", key=f"{state_key}::docall::{call_id}",
        disabled=error is not None,
    )
    result_key = f"{state_key}::callresult::{call_id}"
    if call and parsed_body is not None:
        try:
            with st.spinner(f"Вызов {path}..."):
                response = client.post(path, parsed_body)
        except ApiError as exc:
            st.session_state[result_key] = ("error", str(exc))
        else:
            st.session_state[result_key] = ("ok", response)

    result = st.session_state.get(result_key)
    if result:
        status, payload = result
        if status == "ok":
            st.success("Вызов выполнен.")
            if isinstance(payload, (dict, list)):
                st.json(payload)
            else:
                st.code(str(payload), wrap_lines=True)
        else:
            st.error(payload)


def _render_body_assembly(
    flows: list[dict], service_topics: Counter, state_key: str, client: ApiClient,
) -> None:
    """Сборка body/query одного выбранного вызова microservice_call (topic → вызов)."""
    if not service_topics:
        st.info("В service_task нет действий microservice_call.")
        return

    topics = [t for t, _ in service_topics.most_common()]
    topic = st.selectbox("Topic", topics, key=f"{state_key}::bodytopic")

    calls = _microservice_calls(flows, topic)
    if not calls:
        st.info("Для выбранного topic нет вызовов.")
        return

    # подпись → вызов; при повторе id добавляем порядковый индекс для различения
    labels: list[str] = []
    by_label: dict[str, tuple[dict, dict, dict[str, dict]]] = {}
    for i, (node, action, idx) in enumerate(calls):
        name = (node.get("data") or {}).get("name")
        label = f"{_short(node.get('id'))}"
        if name:
            label += f" · {name}"
        if label in by_label:
            label += f" #{i}"
        labels.append(label)
        by_label[label] = (node, action, idx)

    chosen = st.selectbox("Вызов", labels, key=f"{state_key}::bodycall")
    node, action, idx = by_label[chosen]
    data = action.get("data") or {}

    st.caption(f"`{data.get('service_topic', '—')}` · узел `{node.get('id', '?')}`")

    doc_cache = st.session_state.setdefault(f"{state_key}::doccache", {})
    with st.spinner("Загрузка связанных документов..."):
        body = assemble(data.get("body"), idx, client, doc_cache)
        query = assemble(data.get("query"), idx, client, doc_cache)

    st.markdown("**Собранный `body`:**")
    if body:
        st.json(body)
    else:
        st.caption("body пуст или отсутствует.")

    st.markdown("**Собранный `query`:**")
    if query:
        st.json(query)
    else:
        st.caption("query пуст или отсутствует.")

    action_name = (data.get("service_topic") or "").rsplit(".", 1)[-1]
    call_id = f"{node.get('id')}::{action.get('id')}"

    st.divider()
    _render_call_section(client, action_name, body, state_key, call_id)

    st.divider()
    _render_test_files_check(client, data.get("service_topic"), body, state_key)


def render(
    rows: list[dict], state_key: str, client: ApiClient, *, show_picker: bool = True,
) -> None:
    """Рисует панель разбора flow (если в строках есть flow с nodes).

    show_picker=False пропускает выбор процесса и использует все переданные
    rows как есть — для страниц с уже одним конкретным процессом (см.
    el_integration.py), где выбор из одного варианта был бы лишним."""
    flows_with_rows = _flows_with_rows(rows)
    if not flows_with_rows:
        return

    st.divider()
    st.markdown("### 🔀 Разбор flow процесса")
    st.caption(
        "Узлы графа процесса по типам; узлы `service_task` — по типам действий; "
        "действия `microservice_call` — по `service_topic`."
    )

    if show_picker:
        all_label = f"— Все процессы (сумма: {len(flows_with_rows)}) —"
        options = [all_label] + [
            _process_label(row, i) for i, (row, _) in enumerate(flows_with_rows)
        ]
        choice = st.selectbox("Процесс", options, key=f"{state_key}::flowpick")

        if choice == all_label:
            selected = [flow for _, flow in flows_with_rows]
        else:
            selected = [flows_with_rows[options.index(choice) - 1][1]]
    else:
        selected = [flow for _, flow in flows_with_rows]

    stats = analyze(selected)
    node_types = stats["node_types"]
    action_types = stats["action_types"]
    service_topics = stats["service_topics"]

    m1, m2, m3 = st.columns(3)
    m1.metric("Узлов всего", sum(node_types.values()))
    m2.metric("Узлов service_task", node_types.get("service_task", 0))
    m3.metric("Действий microservice_call", sum(service_topics.values()))

    tab_nodes, tab_actions, tab_topics, tab_body = st.tabs(
        ["Типы узлов", "service_task → действия",
         "microservice_call → topic", "Сборка body/query"]
    )
    with tab_nodes:
        _render_section(node_types, "тип узла", "В flow нет узлов.")
    with tab_actions:
        _render_section(
            action_types, "тип действия",
            "В выбранных процессах нет узлов service_task с действиями.",
        )
    with tab_topics:
        _render_section(
            service_topics, "service_topic",
            "В service_task нет действий microservice_call.",
        )
        if service_topics:
            topics = [t for t, _ in service_topics.most_common()]
            topic = st.selectbox(
                "Показать узлы для topic", topics, key=f"{state_key}::topicpick",
            )
            matched = nodes_for_topic(selected, topic)
            st.caption(f"Узлов с topic `{topic}`: {len(matched)}")
            for i, node in enumerate(matched):
                name = (node.get("data") or {}).get("name")
                head = f"{node.get('type', '—')} · {node.get('id', '?')}"
                if name:
                    head += f" · {name}"
                with st.expander(head, expanded=(i == 0)):
                    st.json(node)

    with tab_body:
        _render_body_assembly(selected, service_topics, state_key, client)
