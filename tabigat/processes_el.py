"""Страница «Процессы с ЕЛ»: разбор elicense чисто по локальным XML-файлам.

Работает без обращения к API процессов/issued-service-registry (которое
может быть недоступно или медленным) — никад заявления и связанные файлы
(типы demand/nikad_document/pdf, что соответствует топикам send_demand/
get_document_nikad/send_document) берутся прямо из локального индекса папки
xmls/ (см. xml_files.py). Кнопка «Синхронизация» подтягивает новые файлы с
сервера (search-by-date-range + download), но сама страница работает и без
неё — единственный сетевой вызов на странице необязателен.

Найденные файлы разбираются на SOAP-элементы (см. SOAP_ELEMENTS) с пометкой
error/success по тексту внутри (см. parse_soap_elements) — SOAP-конверты
заворачивают бизнес-payload как экранированную XML-строку в несколько
уровней подряд, это разворачивает xml_files.find_all_elements.

Топики выполняются последовательно, поэтому успех более позднего топика
доказывает успех предыдущих, даже если их файлов нет — такой выведенный
статус помечается отдельно (см. _apply_success_implication).

Разобранные никады можно отложить с примечанием — пометка живёт локально и
статусы не меняет, только позволяет убрать их из списка фильтром
(см. deferrals, _render_defer_section).

В детализации по никаду — две операции по явному запросу пользователя (не
автоматически, чтобы не зависеть от отзывчивости API процессов):
  - поиск ref процесса (issued-service-registry.application_info_number →
    process_id → Processes.ref), см. _render_process_lookup; результат
    (ref или «не найден») запоминается и попадает в колонку «Ref» таблицы,
    см. process_refs;
  - повторная отправка последней попытки — тело запроса собирается из flow
    найденного процесса (flow_breakdown.body_for_topic, то же тело, что и на
    странице «Интеграция с ЕЛ») и доступно для правки перед отправкой;
    пока процесс не найден, показывается неполное приближение из XML
    (см. _resend_body, _BODY_EXTRACTORS).
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from typing import Any

import pandas as pd
import streamlit as st

from . import (
    auth, deferrals, flow_breakdown, issued_service_registry, process_refs, xml_files,
)
from .api import ApiClient, ApiError

PROCESSES_PATH = "/api/v1/processes/main/processes"

# kind (см. xml_files.NIKAD_ELEMENT_BY_KIND) → человекочитаемая подпись вкладки/колонки
_KIND_LABELS = {
    "demand": "send_demand",
    "nikad_document": "get_document_nikad",
    "pdf": "send_document",
}

# kind'ы в порядке фактического выполнения — на этом порядке держится вывод
# статуса «по следствию» (см. _apply_success_implication)
_KIND_SEQUENCE = ("demand", "nikad_document", "pdf")
_KIND_LABEL_LIST = [_KIND_LABELS[kind] for kind in _KIND_SEQUENCE]

_STATUS_ICON = {
    "error": "🔴", "success": "🟢", "implied": "🟩", "neutral": "⚪", "missing": "—",
}
# статусы, которые считаются успехом (в т.ч. выведенный по следующему шагу)
_SUCCESS_STATUSES = {"success", "implied"}

# SOAP-элементы, которые ищем внутри содержимого тестовых файлов.
# Fault — транспортный сбой самой шины BIP (SOAP-ENV:Fault вместо бизнес-ответа):
# бизнес-элементов в таком ответе нет вообще, поэтому без него файл выглядел бы
# «без статуса», хотя это ошибка.
SOAP_ELEMENTS = {
    "TransferDemandRequest", "BusinessResponse", "PutBusinessRequest",
    "BusinessRequest", "PutSystemRequest", "PutSystemRequestResponse",
    "TransferDocumentRequest", "TransferDocumentResponse", "Fault",
}

# человекочитаемые поля ошибки, которые ищем внутри найденного элемента —
# в этом порядке (см. реальный пример: BusinessResponse → ErrorInfo →
# ErrorMessage/ErrorDescription)
_ERROR_TEXT_FIELDS = ("errormessage", "errordescription", "faultstring", "message", "description")
# код ошибки — в порядке предпочтения: errorCode шины (SCE013) информативнее,
# чем faultcode SOAP-конверта (обычно просто SOAP-ENV:Server)
_ERROR_CODE_FIELDS = ("errorcode", "faultcode")
# сюда шина кладёт ответ чужого сервиса целиком — в SOAP-ENV:Fault это HTML-
# страница с реальной причиной, из неё берём только заголовок (см. _html_title)
_ERROR_DATA_FIELDS = ("errordata",)

_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)

# элемент-заглушка для ответа, который вообще не XML (например HTML-страница
# «502 Bad Gateway» от прокси) — файл есть, но SOAP-конверта в нём нет
_NON_SOAP_ELEMENT = "не SOAP-ответ"


def _html_title(text: str) -> str:
    """Заголовок HTML-страницы — самое содержательное в ответах-страницах
    ошибок («502 Bad Gateway», «Access to the path ... is denied»)."""
    match = _TITLE_RE.search(text)
    return html.unescape(match.group(1)).strip() if match else ""


def _extract_error_text(fragment: str) -> str:
    """Читаемый текст ошибки: код + сообщение из явных полей, плюс суть
    вложенного ответа чужого сервиса, если он попал в errorData. Если явных
    полей нет — любой элемент с 'error' в имени, иначе весь фрагмент."""
    try:
        root = ET.fromstring(fragment)
    except ET.ParseError:
        return fragment.strip()

    codes: dict[str, str] = {}
    parts: list[str] = []
    nested = ""
    for elem in root.iter():
        name = xml_files.local_name(elem.tag).lower()
        text = (elem.text or "").strip()
        if not text:
            continue
        if name in _ERROR_CODE_FIELDS:
            codes.setdefault(name, text)
        elif name in _ERROR_TEXT_FIELDS:
            # faultstring и errorMessage у Fault обычно дублируют друг друга
            if text not in parts:
                parts.append(text)
        elif name in _ERROR_DATA_FIELDS and not nested:
            nested = _html_title(text)

    code = next((codes[field] for field in _ERROR_CODE_FIELDS if field in codes), "")
    message = " — ".join(parts)
    if code:
        message = f"{code}: {message}" if message else code
    if nested:
        message = f"{message} — {nested}" if message else nested
    if message:
        return message

    for elem in root.iter():
        if "error" in xml_files.local_name(elem.tag).lower() and (elem.text or "").strip():
            return elem.text.strip()

    return fragment.strip()


def parse_soap_elements(xml_text: str) -> list[dict[str, Any]]:
    """Ищет SOAP_ELEMENTS в содержимом файла (см. xml_files.find_all_elements —
    разворачивает вложенные экранированные XML-строки); для каждого — статус
    (error/success/neutral) по наличию соответствующего текста внутри.

    Содержимое, которое вообще не XML (HTML-страница ошибки от прокси),
    отдаётся одним элементом-заглушкой со статусом error: искать в нём нечего,
    но это сбой, а не «нет статуса»."""
    found = xml_files.find_all_elements(xml_text, SOAP_ELEMENTS)
    if not found and xml_text.strip() and not xml_files.looks_like_xml(xml_text):
        content = xml_text.strip()
        return [{
            "element": _NON_SOAP_ELEMENT, "status": "error", "content": content,
            "detail": _html_title(content) or content[:200],
        }]

    results = []
    for name, fragment in found:
        low = fragment.lower()
        if "error" in low:
            status, detail = "error", _extract_error_text(fragment)
        elif "success" in low:
            status, detail = "success", fragment.strip()
        else:
            status, detail = "neutral", fragment.strip()
        results.append({"element": name, "status": status, "content": fragment, "detail": detail})
    return results


def _render_soap_elements(elements: list[dict[str, Any]]) -> None:
    if not elements:
        st.caption("Искомые SOAP-элементы в файле не найдены.")
        return
    icons = {"error": "🔴", "success": "🟢", "neutral": "⚪"}
    for el in elements:
        status = el["status"]
        with st.expander(f"{icons[status]} {el['element']}", expanded=(status == "error")):
            if status == "error":
                st.error(el["detail"])
                if el["detail"] != el["content"].strip():
                    st.code(el["content"], language="xml", wrap_lines=True)
            elif status == "success":
                st.success("success")
                st.code(el["content"], language="xml", wrap_lines=True)
            else:
                st.code(el["content"], language="xml", wrap_lines=True)


def _render_sync_section(client: ApiClient) -> None:
    """Работа с папкой xmls/: синхронизация с сервером (search-by-date-range от
    даты последнего локального файла до сейчас, скачивает недостающие) и сброс
    кэшей после ручной правки папки. Обе операции необязательные — остальная
    часть страницы работает без них."""
    st.markdown("### 🔄 Тестовые файлы")
    latest = xml_files.latest_local_timestamp()
    st.caption(
        f"Локально файлов: {len(xml_files.all_local_filenames())}"
        + (f" · последний: `{latest:%d.%m.%Y %H:%M}`" if latest else "")
    )

    sync_col, rescan_col = st.columns(2)
    sync = sync_col.button(
        "🔄 Синхронизировать с сервером", key="processes_el::sync",
        use_container_width=True, disabled=latest is None,
    )
    rescan = rescan_col.button(
        "🔃 Перечитать папку `xmls/`", key="processes_el::rescan", use_container_width=True,
        help="Индекс файлов и таблица статусов кэшируются на всё время работы "
             "приложения — нажмите после ручного добавления/удаления файлов в папке.",
    )

    if rescan:
        # индекс никадов (xml_files) и таблица статусов (эта страница) —
        # два независимых кэша, сбрасывать нужно оба
        xml_files.invalidate_index()
        invalidate_cache()
        st.success("Папка перечитана заново.")

    if latest is None:
        st.caption(
            "Локальных файлов нет — не от какой даты начинать синхронизацию. "
            "Добавьте хотя бы один файл в `xmls/` вручную и нажмите «🔃 Перечитать папку»."
        )
        return

    if sync:
        try:
            with st.spinner("Поиск и скачивание новых файлов (может занять до минуты)..."):
                result = xml_files.sync_from_server(client, latest)
        except ApiError as exc:
            st.error(str(exc))
        else:
            if result["downloaded"]:
                invalidate_cache()
            st.success(
                f"На сервере за период: {result['found']} · "
                f"новых: {result['missing']} · скачано: {len(result['downloaded'])}"
            )
            if result["errors"]:
                st.warning(f"Не удалось скачать {len(result['errors'])} файлов.")
                with st.expander("Ошибки скачивания"):
                    for fname, msg in result["errors"].items():
                        st.caption(f"`{fname}`: {msg}")


def _nikad_files_flat(files_by_kind: dict[str, list[str]]) -> list[str]:
    return [f for files in files_by_kind.values() for f in files]


def _group_by_attempt(files: list[str]) -> list[tuple[dt.datetime | None, list[str]]]:
    """Группирует файлы по временной метке (request+response одной попытки
    делят её) и сортирует по возрастанию — от самой старой попытки к свежей."""
    by_ts: dict[dt.datetime | None, list[str]] = {}
    for f in files:
        by_ts.setdefault(xml_files.filename_timestamp(f), []).append(f)
    return sorted(by_ts.items(), key=lambda kv: kv[0] or dt.datetime.min)


def _kind_status(files: list[str]) -> str:
    """Статус по САМОЙ СВЕЖЕЙ попытке этого kind — если проблема была
    устранена повторным запросом (несколько попыток на один топик), статус
    зелёный, а не красный за уже неактуальную старую ошибку."""
    if not files:
        return "missing"
    attempts = _group_by_attempt(files)
    _, latest_files = attempts[-1]

    statuses: set[str] = set()
    for filename in latest_files:
        content = xml_files.read_local(filename)
        if content is None:
            continue
        statuses.update(el["status"] for el in parse_soap_elements(content))
    if "error" in statuses:
        return "error"
    if "success" in statuses:
        return "success"
    return "neutral"


def _apply_success_implication(statuses: dict[str, str]) -> dict[str, str]:
    """Проставляет статус «успех по следствию» (implied) предыдущим топикам.

    Топики выполняются строго последовательно (_KIND_SEQUENCE: send_demand →
    get_document_nikad → send_document), поэтому успех более позднего невозможен
    без успеха предыдущего. Если следующий топик успешен, а у предыдущего
    успеха не видно (файлы не сохранились/затерялись — самый частый случай, либо
    сохранилась только неудачная попытка), предыдущий фактически прошёл: такой
    статус помечается отдельно от наблюдаемого успеха, чтобы было видно, что он
    выведен, а не подтверждён файлом."""
    result = dict(statuses)
    later_success = False
    for kind in reversed(_KIND_SEQUENCE):
        if result[kind] in _SUCCESS_STATUSES:
            later_success = True
        elif later_success:
            result[kind] = "implied"
    return result


def _status_table() -> tuple[dict[str, Any], ...]:
    """Таблица статусов для текущего состояния папки xmls/ (см. xml_files.folder_version)."""
    return _build_status_table(xml_files.folder_version())


@lru_cache(maxsize=1)
def _build_status_table(version: int) -> tuple[dict[str, Any], ...]:
    """Один ряд на никад: дата последнего файла + статус по каждому kind.

    Кэшируется на уровне процесса (папка большая — разбор SOAP каждого файла
    не бесплатный) и строится заново, как только в папке появились или
    пропали файлы (version — folder_version). Раньше кэш сбрасывался только
    вручную, и таблица отставала от детализации, которая видит свежие файлы."""
    rows = []
    for nikad, files_by_kind in xml_files.local_nikads().items():
        statuses = _apply_success_implication({
            kind: _kind_status(files_by_kind.get(kind, [])) for kind in _KIND_SEQUENCE
        })
        row: dict[str, Any] = {
            "Никад": nikad,
            "Дата": xml_files.latest_timestamp_for(_nikad_files_flat(files_by_kind)),
        }
        for kind in _KIND_SEQUENCE:
            row[_KIND_LABELS[kind]] = statuses[kind]
        rows.append(row)
    rows.sort(key=lambda r: r["Дата"] or dt.datetime.min, reverse=True)
    return tuple(rows)


def invalidate_cache() -> None:
    """Принудительно сбрасывает кэш таблицы статусов (обычно не нужно — см. _status_table)."""
    _build_status_table.cache_clear()


# Успешным считается только зелёный success (в т.ч. выведенный по следующему
# шагу — implied); error/neutral/missing — неуспешно.
_FILTER_OPTIONS = ("Все", "✅ Успешно", "❌ Неуспешно")


def _matches_filter(status: str, choice: str) -> bool:
    if choice == "✅ Успешно":
        return status in _SUCCESS_STATUSES
    if choice == "❌ Неуспешно":
        return status not in _SUCCESS_STATUSES
    return True


_DEFER_OPTIONS = ("Все", "Без отложенных", "Только отложенные")


def _matches_defer_filter(is_deferred: bool, choice: str) -> bool:
    if choice == "Без отложенных":
        return not is_deferred
    if choice == "Только отложенные":
        return is_deferred
    return True


def _render_filters() -> tuple[dict[str, str], str]:
    """Фильтры над таблицей: «успешно/неуспешно» по каждому топику + отложенные.
    Все заданные фильтры работают по И (строка должна подойти под все сразу)."""
    cols = st.columns(len(_KIND_LABEL_LIST) + 1)
    by_topic = {
        label: col.selectbox(label, _FILTER_OPTIONS, key=f"processes_el::filter::{label}")
        for label, col in zip(_KIND_LABEL_LIST, cols)
    }
    defer_choice = cols[-1].selectbox(
        "⏸ Отложенные", _DEFER_OPTIONS, key="processes_el::filter::deferred",
    )
    return by_topic, defer_choice


def _procinfo_key(nikad: str) -> str:
    return f"processes_el::procinfo::{nikad}"


def _render_process_lookup(
    client: ApiClient, nikad: str, saved: dict[str, Any] | None = None,
) -> None:
    """Ref процесса по никаду — только по явному клику (issued-service-registry
    →process_id → Processes.get_one → ref), не автоматически при открытии
    детализации, чтобы не зависеть от отзывчивости этого API.

    Найденный процесс запоминается в session_state целиком: его flow — источник
    полного тела для повторной отправки (см. _resend_body). Результат поиска
    (ref/«не найден») дополнительно пишется в локальный справочник, чтобы
    попадать в колонку «Ref» таблицы и жить дольше сессии (см. process_refs)."""
    key = _procinfo_key(nikad)
    if st.button("🔍 Найти процесс (ref)", key=f"processes_el::findproc::{nikad}"):
        rows = issued_service_registry.load_for_nikad(client, nikad)
        if rows is not None:
            process_id = next((r.get("process_id") for r in rows if r.get("process_id")), None)
            if process_id is None:
                st.session_state[key] = {"found": False}
                process_refs.remember_not_found(nikad)
            else:
                try:
                    process = client.get_one(PROCESSES_PATH, process_id)
                except ApiError as exc:
                    st.session_state[key] = {"error": str(exc)}
                else:
                    st.session_state[key] = {
                        "found": True, "process_id": process_id,
                        "ref": process.get("ref"), "status": process.get("status"),
                        "process": process,
                    }
                    process_refs.remember(
                        nikad, process_id, process.get("ref"), process.get("status"),
                    )
            # таблица нарисована выше этой секции — без перезапуска новый ref
            # появился бы в ней только после следующего действия пользователя
            st.rerun()

    # в session_state результат только за текущую сессию; после перезапуска
    # берём сохранённый (см. process_refs) — он же показан в колонке «Ref»
    info = st.session_state.get(key) or saved
    if info is None:
        return
    if "error" in info:
        st.error(info["error"])
    elif not info.get("found"):
        st.info("Запись issued-service-registry с этим никадом не найдена.")
    else:
        st.markdown(
            f"**process_id:** `{info['process_id']}` · **ref:** `{info['ref']}` · "
            f"**статус:** `{info['status']}`"
        )
    if info is saved and info.get("at"):
        st.caption(f"Результат поиска от `{info['at']}` — нажмите кнопку, чтобы обновить.")


def _xget(content: str, name: str) -> str:
    return xml_files.find_element_text(content, name) or ""


def _extract_demand_body(content: str) -> dict[str, str]:
    """Лучшее приближение GbdElTransferDemandDto из TransferDemandRequest.

    Часть полей (org_name_kz/ru, street, place, region, district, iin,
    first_name/last_name/father_name) не определяются однозначно по имени
    элемента — в XML они вложены под Ru/Kz-подэлементами разных родителей
    (FullName/Ru, Street/Ru, Place/Ru и т.д. называются одинаково), поэтому
    оставлены пустыми. Проверьте и заполните перед отправкой."""
    return {
        "nikad": _xget(content, "IdentificationNumber"),
        "create_date": _xget(content, "CreateDate"),
        "licensor_code": _xget(content, "LicensorCode"),
        "iin": "",
        "first_name": "",
        "last_name": "",
        "father_name": "",
        "bin": _xget(content, "Bin"),
        "org_name_kz": "",
        "org_name_ru": "",
        "position_representative": _xget(content, "PositionRepresentative"),
        "postal_index": _xget(content, "PostalIndex"),
        "street": "",
        "building_number": _xget(content, "BuildingNumber"),
        "apartament_number": _xget(content, "ApartamentNumber"),
        "phone_number": _xget(content, "PhoneNumber"),
        "country": "",
        "place": "",
        "region": "",
        "district": "",
    }


def _extract_nikad_document_body(content: str) -> dict[str, str]:
    """GbdElNikadDocumentDto из DocumentNumberRequest — один однозначный field."""
    return {"number": _xget(content, "RequestNumber")}


def _extract_pdf_body(content: str) -> dict[str, str]:
    """GbdElTransferDocumentDto из TransferDocumentRequest — все 4 поля
    определяются однозначно по имени элемента."""
    return {
        "request_identification_number": _xget(content, "RequestIdentificationNumber"),
        "identification_number": _xget(content, "IdentificationNumber"),
        "issue_date": _xget(content, "IssueDate"),
        "doc_id": _xget(content, "DocumentIdentificationNumber"),
    }


_BODY_EXTRACTORS = {
    "demand": _extract_demand_body,
    "nikad_document": _extract_nikad_document_body,
    "pdf": _extract_pdf_body,
}

# kind'ы, у которых не все поля DTO извлекаются однозначно из XML — предупреждаем
_PARTIAL_EXTRACTION_KINDS = {"demand"}

# Дополнительные варианты повторной отправки: топик → {подпись: (путь, поля,
# которых нет в теле основного топика)}.
# По заявлению вместо выдачи документа может уходить отказ (send-rejection):
# тело то же (request_identification_number/identification_number/issue_date/
# doc_id), плюс причина отказа на двух языках.
_EXTRA_RESEND_VARIANTS: dict[str, dict[str, tuple[str, dict[str, str]]]] = {
    "pdf": {
        "send_rejection": (
            "/api/v1/integrations/elicense/send-rejection",
            {"reason_ru": "-", "reason_kz": "-"},
        ),
    },
}


def _resend_variants(kind: str) -> dict[str, tuple[str, dict[str, str]]]:
    """{подпись: (путь, доп. поля тела)} — чем можно переотправить этот топик.
    Первый вариант всегда сам топик (см. flow_breakdown.TOPIC_CALL_PATHS)."""
    action_name = _KIND_LABELS[kind]
    path = flow_breakdown.TOPIC_CALL_PATHS.get(action_name)
    own = {action_name: (path, {})} if path else {}
    return {**own, **_EXTRA_RESEND_VARIANTS.get(kind, {})}


def _resend_body(
    client: ApiClient, nikad: str, kind: str, request_content: str | None,
    actions: list[str],
) -> tuple[dict[str, Any], str]:
    """Тело для повторной отправки и источник, из которого оно получено.

    Основной источник — flow процесса (то же тело, что собирает страница
    «Интеграция с ЕЛ»): именно оно уходит в REST-эндпоинт топика. XML-файл
    для этого не годится — его пишет уже следующий сервис по своей схеме,
    тело в него напрямую не попадает, поэтому обратная сборка из XML
    неполная (см. _BODY_EXTRACTORS) и используется только как запасной
    вариант, пока процесс не найден.

    actions — топики в порядке предпочтения: для отказа сперва ищем во flow
    вызов самого send_rejection (там уже заполнена реальная причина), и лишь
    если его нет — берём тело выдачи документа.

    request_content = None означает, что XML-файла запроса нет (топик мог не
    дойти до отправки) — тогда единственный источник это flow. Источник
    возвращается как "flow:<топик>", "xml" или "none"."""
    info = st.session_state.get(_procinfo_key(nikad)) or {}
    process = info.get("process")
    if process:
        doc_cache = st.session_state.setdefault("processes_el::doccache", {})
        with st.spinner("Сборка тела из flow процесса..."):
            for action in actions:
                body = flow_breakdown.body_for_topic(process, action, client, doc_cache)
                if body:
                    return body, f"flow:{action}"

    extractor = _BODY_EXTRACTORS.get(kind)
    if request_content is None or extractor is None:
        return {}, "none"
    return extractor(request_content), "xml"


_DOCS_PATH = "/api/v1/docs/main/docs"


def _maybe_json(value: Any) -> Any:
    """JSON-строку (в логах документа signatures лежат строкой) разворачивает в объект."""
    if isinstance(value, str) and value.lstrip()[:1] in ("{", "["):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            pass
    return value


def _doc_signatures(doc: dict) -> list[dict[str, Any]]:
    """Подписи документа в порядке ключей — так же, как их видит бэкенд.

    Поле signatures — {"<ИИН>_<время>": {...}}; у каждой подписи свой PDF,
    который подписывали (pdf_bucket/pdf_filename, pdf_hash), CMS (cms_*) и,
    если уже собран, PDF со штампами подписей (signed_pdf_*).

    Порядок важен: send-document (svc_integrations, getSignedDocument) берёт
    signed_pdf_* последней подписи, а скачивание в шлюзе и перегенерация PDF
    на фронте — первой. При двух подписях они расходятся (см. _render_signed_pdf_fix)."""
    raw = _maybe_json(doc.get("signatures"))
    if not isinstance(raw, dict):
        return []
    return [{"key": key, **val} for key, val in raw.items() if isinstance(val, dict)]


def _sig_file(sig: dict[str, Any], prefix: str) -> str | None:
    """`bucket/filename` файла подписи (prefix — pdf/cms/signed_pdf) или None."""
    bucket, name = sig.get(f"{prefix}_bucket"), sig.get(f"{prefix}_filename")
    return f"{bucket}/{name}" if bucket and name else None


_SIGNED_PDF_FIELDS = ("signed_pdf_bucket", "signed_pdf_filename", "signed_pdf_originalname")


def _render_signed_pdf_fix(
    client: ApiClient, doc_id: str, doc: dict, sigs: list[dict[str, Any]],
) -> None:
    """Копирует signed_pdf_* первой подписи в последнюю (PATCH документа).

    Фронт привязывает перегенерированный PDF к первой подписи, а send-document
    читает последнюю — при двух подписях у последней bucket пустой. Поля
    копируются, а не переносятся: шлюз отдаёт PDF по первой подписи, и
    checksum, который считает send-document, должен совпасть с этим файлом.
    Объект signatures отправляется целиком — так же, как это делает фронт."""
    first, last = sigs[0], sigs[-1]
    source = {field: first[field] for field in _SIGNED_PDF_FIELDS if first.get(field)}
    st.markdown("**Исправление записи:**")
    st.caption(
        f"Скопировать в последнюю подпись (`{last.get('timestamp') or last['key']}`) "
        f"подписанный PDF первой (`{first.get('timestamp') or first['key']}`). "
        f"Запрос `PATCH {_DOCS_PATH}/{doc_id}` на `{client.base_url}`."
    )
    st.json(source, expanded=True)

    confirm_key = f"processes_el::pdffixconfirm::{doc_id}"
    confirm = st.checkbox("Подтверждаю запись в документ", key=confirm_key)
    fix = st.button(
        "🩹 Привязать подписанный PDF к последней подписи",
        key=f"processes_el::pdffix::{doc_id}", disabled=not confirm,
    )
    if not fix:
        return

    signatures = _maybe_json(doc.get("signatures"))
    signatures = {**signatures, last["key"]: {**signatures[last["key"]], **source}}
    try:
        with st.spinner("Сохранение..."):
            client.update(_DOCS_PATH, doc_id, {"signatures": signatures})
    except ApiError as exc:
        st.error(str(exc))
        return
    # документ перечитывается заново, чтобы проверка показала то, что реально сохранилось
    st.session_state["processes_el::pdfcheck"].pop(doc_id, None)
    st.session_state[f"processes_el::pdffixdone::{doc_id}"] = True
    st.session_state.pop(confirm_key, None)
    st.rerun()


def _render_doc_pdf_check(client: ApiClient, doc_id: str) -> None:
    """Перед send_document показывает подписи документа и их PDF в хранилище.

    send-document берёт подписанный PDF (signed_pdf_*) последней подписи и
    достаёт его из MinIO; если полей нет, бэкенд падает с 500
    InvalidBucketNameError. Если PDF при этом есть у первой подписи —
    предлагает исправить запись (см. _render_signed_pdf_fix)."""
    cache = st.session_state.setdefault("processes_el::pdfcheck", {})
    if st.button("↻ Перепроверить документ", key=f"processes_el::pdfrecheck::{doc_id}"):
        cache.pop(doc_id, None)
    if doc_id not in cache:
        try:
            with st.spinner("Проверка документа..."):
                cache[doc_id] = client.get_one(_DOCS_PATH, doc_id)
        except ApiError as exc:
            cache[doc_id] = exc
    doc = cache[doc_id]

    if isinstance(doc, ApiError):
        st.warning(f"Не удалось загрузить документ `{doc_id}` для проверки PDF: {doc}")
        return
    if not isinstance(doc, dict):
        st.warning(f"Неожиданный ответ на запрос документа `{doc_id}`.")
        return

    if st.session_state.pop(f"processes_el::pdffixdone::{doc_id}", False):
        st.success("Подписанный PDF привязан к последней подписи, документ перечитан.")

    sigs = _doc_signatures(doc)
    if not sigs:
        st.error(
            "У документа нет подписей (`signatures` пусто) — подписанного PDF нет, "
            "send-document отправлять нечего."
        )
    else:
        rows = []
        for sig in sigs:
            signer = sig.get("signed_by") or {}
            rows.append({
                "Время": sig.get("timestamp") or sig["key"],
                "Подписант": " ".join(
                    filter(None, (signer.get("last_name"), signer.get("first_name")))
                ) or "—",
                "pdf_hash": str(sig.get("pdf_hash") or "—")[:12],
                "PDF": _sig_file(sig, "pdf") or "—",
                "Подписанный PDF": _sig_file(sig, "signed_pdf") or "—",
            })
        st.markdown("**Подписи документа:**")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        latest = sigs[-1]
        latest_time = latest.get("timestamp") or latest["key"]
        # send-document читает только signed_pdf_* последней подписи; pdf_* —
        # исходный PDF, сохранённый при подписании, для отправки не нужен
        if not _sig_file(latest, "signed_pdf"):
            earlier = [s for s in sigs[:-1] if _sig_file(s, "signed_pdf")]
            st.error(
                f"У последней подписи (`{latest_time}`) нет `signed_pdf_bucket`/"
                "`signed_pdf_filename`, а send-document берёт подписанный PDF именно "
                "из последней подписи — упадёт с `InvalidBucketNameError`."
                + (
                    " У более ранней подписи он при этом есть: "
                    + ", ".join(f"`{s.get('timestamp') or s['key']}`" for s in earlier)
                    + "."
                    if earlier else " Сначала сформируйте PDF на странице документа."
                )
            )
            if _sig_file(sigs[0], "signed_pdf"):
                _render_signed_pdf_fix(client, doc_id, doc, sigs)
        else:
            st.success(f"У последней подписи есть подписанный PDF: `{_sig_file(latest, 'signed_pdf')}`.")
        if not _sig_file(latest, "pdf"):
            st.caption(
                f"У последней подписи (`{latest_time}`) нет `pdf_bucket`/`pdf_filename` — "
                "исходный PDF при подписании не сохранился. Для send-document он не нужен."
            )

        if len(sigs) > 1:
            hashes = {sig.get("pdf_hash") for sig in sigs}
            st.caption(
                f"⚠️ Подписей: {len(sigs)}. "
                + (
                    "У всех разный `pdf_hash` — документ подписывали повторно "
                    "(разные версии PDF), это не дубль одной подписи."
                    if len(hashes) == len(sigs)
                    else "У части подписей одинаковый `pdf_hash` — похоже на дубль одного подписания."
                )
            )

    with st.expander("JSON документа"):
        st.json(doc, expanded=False)


def _render_resend_section(
    client: ApiClient, nikad: str, kind: str, request_content: str | None,
) -> None:
    """Позволяет скорректировать тело запроса и повторно вызвать REST-эндпоинт.
    Аналог flow_breakdown._render_call_section; тело берётся из flow найденного
    процесса, а при его отсутствии — из XML (см. _resend_body). Если у топика
    несколько вариантов отправки (см. _resend_variants) — даёт выбрать, каким
    именно; у каждого варианта своё тело и свой результат вызова."""
    variants = _resend_variants(kind)
    if not variants:
        return

    st.markdown("**Повторная отправка:**")
    if len(variants) > 1:
        variant = st.radio(
            "Метод", list(variants), horizontal=True,
            key=f"processes_el::resendvariant::{nikad}::{kind}",
        )
    else:
        variant = next(iter(variants))
    path, extra_fields = variants[variant]

    key_suffix = f"{nikad}::{kind}::{variant}"
    # сперва ищем во flow вызов выбранного варианта, иначе — вызов самого топика
    body, source = _resend_body(
        client, nikad, kind, request_content,
        list(dict.fromkeys([variant, _KIND_LABELS[kind]])),
    )
    added = [field for field in extra_fields if field not in body]
    body = {**body, **{field: extra_fields[field] for field in added}}

    st.caption(f"`POST {path}`")
    if source == "none":
        st.caption(
            "⚠️ Тело собрать не из чего: файла запроса этого топика нет. "
            "Нажмите «🔍 Найти процесс» выше — тело соберётся из `flow` процесса, "
            "как на странице «Интеграция с ЕЛ», файлы для этого не нужны."
        )
    elif source == "xml":
        st.caption(
            "⚠️ Тело восстановлено из XML и неполное: XML пишет следующий сервис, "
            "тело запроса в него напрямую не попадает. Нажмите «🔍 Найти процесс» "
            "выше, чтобы собрать полное тело из `flow` процесса."
        )
        if kind in _PARTIAL_EXTRACTION_KINDS:
            st.caption("Поля, не определяемые однозначно по XML, оставлены пустыми.")
    else:
        from_action = source.split(":", 1)[1]
        if from_action == variant:
            st.caption("Тело собрано из `flow` процесса — как на странице «Интеграция с ЕЛ».")
        else:
            st.caption(
                f"Во `flow` процесса вызова `{variant}` нет — тело взято из топика "
                f"`{from_action}` (поля у них общие)."
            )
    if added:
        st.caption(
            f"Поля `{'`, `'.join(added)}` в теле топика отсутствуют — подставлено "
            "значение по умолчанию, укажите причину отказа перед отправкой."
        )

    # тело перечитывается заново, когда меняется его источник (например,
    # процесс нашли уже после того, как поле было заполнено из XML);
    # правки пользователя при этом не теряются — источник тот же
    text_key = f"processes_el::resendbody::{key_suffix}"
    source_key = f"processes_el::resendsrc::{key_suffix}"
    if st.session_state.get(source_key) != source:
        st.session_state[source_key] = source
        st.session_state[text_key] = json.dumps(body, ensure_ascii=False, indent=2)

    edited = st.text_area(
        "Тело запроса (можно скорректировать перед отправкой)",
        key=text_key, height=280,
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

    doc_id = parsed_body.get("doc_id") if parsed_body else None
    if isinstance(doc_id, str) and doc_id.strip():
        _render_doc_pdf_check(client, doc_id.strip())

    send = st.button(
        "🚀 Отправить", type="primary", key=f"processes_el::resend::{key_suffix}",
        disabled=error is not None,
    )
    result_key = f"processes_el::resendresult::{key_suffix}"
    if send and parsed_body is not None:
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


# частые причины отложения — кнопки вставляют их в поле примечания, а не
# заменяют его: причин может быть несколько, и к любой можно дописать детали
_DEFER_PRESETS = (
    "не сгенерирован пдф",
    "не принял Вариант ФЛ",
    "проверить отказ",
)


def _insert_defer_preset(note_key: str, preset: str) -> None:
    """Добавляет готовую причину к тексту примечания (повторно — не добавляет)."""
    current = str(st.session_state.get(note_key, "")).strip()
    if not current:
        st.session_state[note_key] = preset
    elif preset not in current:
        st.session_state[note_key] = f"{current}; {preset}"


def _render_defer_section(nikad: str, entry: dict[str, Any] | None) -> None:
    """Пометка «отложен» с примечанием (см. deferrals) — статусы топиков не
    меняются, никад лишь можно убрать из списка фильтром «⏸ Отложенные»."""
    note = deferrals.note_of(entry)
    note_key = f"processes_el::defernote::{nikad}"
    if note_key not in st.session_state:
        st.session_state[note_key] = note

    title = "⏸ Отложить никад"
    if entry:
        title = f"⏸ Отложен: {note or 'без примечания'}"
    with st.expander(title):
        if entry and entry.get("at"):
            st.caption(f"Отложен: `{entry['at']}`")

        # кнопки должны идти до самого поля: значение виджета можно менять
        # только до его создания в этом прогоне
        with st.container(horizontal=True, gap="small"):
            for preset in _DEFER_PRESETS:
                if st.button(
                    preset, key=f"processes_el::preset::{nikad}::{preset}",
                    type="tertiary", icon=":material/add:", width="content",
                    help="Вставить в примечание — текст можно дописать",
                ):
                    _insert_defer_preset(note_key, preset)

        st.text_area(
            "Примечание — почему отложен", key=note_key, height=68,
            label_visibility="collapsed",
            placeholder="Примечание — почему отложен",
        )
        with st.container(horizontal=True, gap="small"):
            save = st.button(
                "💾 Сохранить примечание" if entry else "⏸ Отложить",
                key=f"processes_el::defer::{nikad}", width="content",
            )
            undo = entry is not None and st.button(
                "↩️ Вернуть в работу", key=f"processes_el::undefer::{nikad}",
                type="tertiary", width="content",
            )
        if save:
            deferrals.defer(nikad, st.session_state[note_key])
            st.rerun()
        if undo:
            deferrals.undefer(nikad)
            # состояние виджета удаляем, а не перезаписываем — присваивать
            # значение уже созданному в этом прогоне виджету нельзя
            st.session_state.pop(note_key, None)
            st.rerun()


def _implication_note(kind: str, statuses: dict[str, str]) -> str | None:
    """Пояснение к статусу «успех по следствию»: какой следующий топик его
    доказывает (см. _apply_success_implication)."""
    if statuses.get(_KIND_LABELS[kind]) != "implied":
        return None
    after = _KIND_SEQUENCE[_KIND_SEQUENCE.index(kind) + 1:]
    proof = next(
        (_KIND_LABELS[k] for k in after if statuses.get(_KIND_LABELS[k]) == "success"),
        None,
    )
    return (
        f"🟩 Шаг фактически прошёл успешно: следующий шаг `{proof}` успешен, "
        "а без него это невозможно. Файлы этого топика просто не сохранились."
        if proof else None
    )


def _render_nikad_files(
    client: ApiClient, nikad: str, files_by_kind: dict[str, list[str]],
    statuses: dict[str, str],
) -> None:
    tabs = st.tabs(_KIND_LABEL_LIST)
    for kind, tab in zip(_KIND_SEQUENCE, tabs):
        with tab:
            note = _implication_note(kind, statuses)
            if note:
                st.success(note)

            files = files_by_kind.get(kind, [])
            latest_request_content: str | None = None
            if not files:
                st.info("Файлов этого типа для данного никада нет.")
            else:
                attempts = _group_by_attempt(files)
                multiple = len(attempts) > 1
                for i, (ts, attempt_files) in enumerate(attempts):
                    is_latest = i == len(attempts) - 1
                    if multiple:
                        when = f"{ts:%d.%m.%Y %H:%M}" if ts else "без даты"
                        tag = "текущая" if is_latest else "устаревшая"
                        st.markdown(f"**Попытка {when} ({tag}):**")
                    for filename in attempt_files:
                        content = xml_files.read_local(filename)
                        st.markdown(f"`{filename}`")
                        if content is None:
                            st.error("Не удалось прочитать файл.")
                            continue
                        _render_soap_elements(parse_soap_elements(content))
                        if is_latest and xml_files.parse_filename(filename) == (kind, "request"):
                            latest_request_content = content
                    if multiple and not is_latest:
                        st.divider()

            # секция отправки нужна и без файлов: тело собирается из flow
            # процесса (см. _resend_body), XML для этого не обязателен — как
            # раз топики, до которых дело не дошло, и надо переотправлять
            st.divider()
            _render_resend_section(client, nikad, kind, latest_request_content)


def render(client: ApiClient) -> None:
    st.title("📮 Процессы с ЕЛ")
    auth.account_sidebar(client)
    st.caption(
        "Работает по локальным файлам `xmls/` — без обращения к API "
        "процессов/issued-service-registry."
    )

    _render_sync_section(client)
    st.divider()

    with st.spinner("Разбор локальных файлов..."):
        all_rows = _status_table()
    if not all_rows:
        st.info("В папке `xmls/` пока нет файлов. Запустите синхронизацию выше.")
        return

    deferred = deferrals.load()
    refs = process_refs.load()
    filters, defer_choice = _render_filters()
    rows = [
        r for r in all_rows
        if all(_matches_filter(r[label], choice) for label, choice in filters.items())
        and _matches_defer_filter(r["Никад"] in deferred, defer_choice)
    ]

    st.markdown(
        f"**Найдено никадов:** {len(rows)} из {len(all_rows)} · отложено: {len(deferred)}"
    )
    st.caption(" · ".join(f"{icon} {name}" for name, icon in [
        ("успех", "🟢"), ("успех по следующему шагу", "🟩"), ("ошибка", "🔴"),
        ("без статуса", "⚪"), ("нет файлов", "—"), ("отложен", "⏸"),
    ]))
    st.caption(
        "Колонка «Ref» заполняется по кнопке «🔍 Найти процесс» в детализации "
        f"никада (`{process_refs.NOT_FOUND_LABEL}` — процесса с таким никадом нет); "
        "пусто — поиск ещё не запускали."
    )
    if not rows:
        st.info("Под заданные фильтры не подходит ни один никад.")
        return

    display_df = pd.DataFrame(
        [
            {
                "Никад": r["Никад"],
                "Ref": process_refs.ref_label(refs.get(r["Никад"])),
                "Дата": f"{r['Дата']:%d.%m.%Y %H:%M}" if r["Дата"] else "—",
                **{label: _STATUS_ICON[r[label]] for label in _KIND_LABEL_LIST},
                "⏸": "⏸" if r["Никад"] in deferred else "",
                "Примечание": deferrals.note_of(deferred.get(r["Никад"])),
            }
            for r in rows
        ]
    )

    event = st.dataframe(
        display_df, use_container_width=True, hide_index=True,
        selection_mode="single-row", on_select="rerun", key="processes_el::table",
    )
    selected = [i for i in event.selection.rows if i < len(rows)]
    if not selected:
        st.info("Выберите строку в таблице, чтобы увидеть разбор файлов по этому никаду.")
        return

    row = rows[selected[0]]
    nikad = row["Никад"]
    files_by_kind = xml_files.local_nikads()[nikad]

    st.divider()
    st.markdown(f"### Никад `{nikad}`")
    _render_defer_section(nikad, deferred.get(nikad))
    _render_process_lookup(client, nikad, refs.get(nikad))
    _render_nikad_files(client, nikad, files_by_kind, row)
