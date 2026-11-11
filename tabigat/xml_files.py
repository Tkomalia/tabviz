"""Тестовые XML-файлы elicense: сначала ищем локально (папка xmls/ в корне
проекта), для остальных — через client.search_test_files/download_test_file
(см. api.py).

Каждый файл идентифицируется никадом заявления — элементом внутри его
содержимого (см. NIKAD_ELEMENT_BY_KIND, найдено разбором реальных файлов):
  - demand_request          → IdentificationNumber
  - pdf_request             → RequestIdentificationNumber
  - nikad_document_request  → RequestNumber

SOAP-конверты (BIP ShepExchangeService) заворачивают бизнес-payload как
ЭКРАНИРОВАННУЮ XML-строку внутри текста другого элемента, причём в несколько
уровней подряд: например `data` (leaf, xsi:type=string) содержит текст
`<PutSystemRequest>...<Data>&lt;DocumentNumberRequest&gt;...&lt;RequestNumber&gt;
...` — после одного разэкранирования это валидный XML с элементом
PutSystemRequest, внутри которого Data — ещё раз экранированный XML с
DocumentNumberRequest/RequestNumber. find_element_text/find_all_elements
рекурсивно разворачивают такие уровни (см. _walk/_collect).
"""
from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import Any

from .api import ApiClient, ApiError

XML_DIR = Path(__file__).resolve().parent.parent / "xmls"

# формат дат для /elicense/test-files/search-by-date-range («ДД.ММ.ГГГГ ЧЧ:ММ»)
_DATE_FORMAT = "%d.%m.%Y %H:%M"

# элемент с никадом заявления, по типу файла (demand/pdf/nikad_document)
NIKAD_ELEMENT_BY_KIND: dict[str, str] = {
    "demand": "IdentificationNumber",
    "pdf": "RequestIdentificationNumber",
    "nikad_document": "RequestNumber",
}

# <YYYYMMDD>_<HHMMSS>_<kind>_<request|response>.xml — kind сравниваем точно
# (не через endswith), иначе 'nikad_demand_request.xml' ложно матчится под
# паттерн 'demand' (оба оканчиваются на '_demand_request.xml').
_FILENAME_RE = re.compile(r"^\d{8}_\d{6}_(?P<kind>.+)_(?P<dir>request|response)\.xml$")


def parse_filename(filename: str) -> tuple[str, str] | None:
    """(kind, direction) из имени файла, например ('demand', 'request')."""
    m = _FILENAME_RE.match(filename)
    return (m.group("kind"), m.group("dir")) if m else None


def response_filename(request_filename: str) -> str:
    return request_filename[: -len("_request.xml")] + "_response.xml"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _try_parse(text: str) -> ET.Element | None:
    text = text.strip()
    if not text.startswith("<"):
        return None
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        return None


def _walk(elem: ET.Element, target_name: str, depth: int) -> str | None:
    """Ищет target_name сначала среди реальных потомков, затем — разворачивая
    экранированные XML-строки внутри текста элементов (может быть несколько
    уровней вложенности)."""
    if local_name(elem.tag) == target_name:
        text = (elem.text or "").strip()
        if text:
            return text
    for child in elem:
        found = _walk(child, target_name, depth)
        if found is not None:
            return found
    if depth > 0:
        text = (elem.text or "").strip()
        if text.startswith("<") and text.endswith(">"):
            nested = _try_parse(text)
            if nested is not None:
                return _walk(nested, target_name, depth - 1)
    return None


def find_element_text(xml_text: str, target_name: str, max_depth: int = 6) -> str | None:
    """Ищет элемент target_name в xml_text — в т.ч. вложенный как экранированная
    XML-строка внутри текста другого элемента, на любую глубину до max_depth."""
    root = _try_parse(xml_text)
    if root is None:
        return None
    return _walk(root, target_name, max_depth)


def looks_like_xml(text: str) -> bool:
    """Разбирается ли содержимое как XML вообще. Ответ может оказаться и не
    SOAP-конвертом — например HTML-страницей «502 Bad Gateway» от прокси
    (см. processes_el.parse_soap_elements)."""
    return _try_parse(text) is not None


def _collect(elem: ET.Element, target_names: set[str], depth: int, out: list[tuple[str, str]]) -> None:
    name = local_name(elem.tag)
    if name in target_names:
        out.append((name, ET.tostring(elem, encoding="unicode")))
    for child in elem:
        _collect(child, target_names, depth, out)
    if depth > 0:
        text = (elem.text or "").strip()
        if text.startswith("<") and text.endswith(">"):
            nested = _try_parse(text)
            if nested is not None:
                _collect(nested, target_names, depth - 1, out)


def find_all_elements(
    xml_text: str, target_names: set[str], max_depth: int = 6,
) -> list[tuple[str, str]]:
    """Все элементы с именем из target_names в xml_text (в т.ч. вложенные как
    экранированные XML-строки, на любую глубину). [(имя, xml-фрагмент), ...]."""
    root = _try_parse(xml_text)
    if root is None:
        return []
    out: list[tuple[str, str]] = []
    _collect(root, target_names, max_depth, out)
    return out


def read_local(filename: str) -> str | None:
    try:
        return (XML_DIR / filename).read_text(encoding="utf-8")
    except OSError:
        return None


def local_request_files(kind: str) -> list[str]:
    """Имена локальных *_request.xml файлов данного типа (demand/pdf/nikad_document)."""
    if not XML_DIR.exists():
        return []
    return [
        p.name for p in XML_DIR.iterdir()
        if p.is_file() and parse_filename(p.name) == (kind, "request")
    ]


def folder_version() -> int:
    """Время изменения папки xmls/ (нс) — меняется при добавлении/удалении
    файла. Ключ кэшей, построенных по папке: как только файлы поменялись
    (синхронизация, ручное копирование, другая сессия), кэш строится заново,
    без ручного сброса. Файлы на месте не перезаписываются (save_local пишет
    только недостающие), поэтому mtime папки достаточно."""
    try:
        return XML_DIR.stat().st_mtime_ns
    except OSError:
        return 0


def _nikad_index() -> dict[str, dict[str, str]]:
    """{kind: {filename: никад}} для текущего состояния папки (см. folder_version)."""
    return _build_nikad_index(folder_version())


@lru_cache(maxsize=1)
def _build_nikad_index(version: int) -> dict[str, dict[str, str]]:
    """{kind: {filename: никад}} для локальных *_request.xml файлов трёх типов.

    Строится заново только при изменении папки (version — folder_version),
    а не при каждом обращении к странице: папка большая — тысячи файлов."""
    index: dict[str, dict[str, str]] = {kind: {} for kind in NIKAD_ELEMENT_BY_KIND}
    for kind, element in NIKAD_ELEMENT_BY_KIND.items():
        for filename in local_request_files(kind):
            content = read_local(filename)
            if content is None:
                continue
            nikad = find_element_text(content, element)
            if nikad:
                index[kind][filename] = nikad
    return index


def invalidate_index() -> None:
    """Принудительно сбрасывает кэш индекса (обычно не нужно — см. folder_version)."""
    _build_nikad_index.cache_clear()


def find_local_for_nikad(kind: str, nikad: str) -> list[str]:
    """Локальные файлы (request + его response, если есть) данного типа с этим
    никадом внутри — по кэшированному индексу (см. _nikad_index). Порядок:
    request, response, request, response, ..."""
    result: list[str] = []
    for filename, found_nikad in _nikad_index().get(kind, {}).items():
        if found_nikad != nikad:
            continue
        result.append(filename)
        resp = response_filename(filename)
        if (XML_DIR / resp).exists():
            result.append(resp)
    return result


def local_nikads() -> dict[str, dict[str, list[str]]]:
    """{никад: {kind: [request, response, ...]}} по локальному индексу.

    Позволяет выбирать никад напрямую из уже скачанных файлов — без обращения
    к API процессов/issued-service-registry (которое может быть недоступно
    или медленным)."""
    result: dict[str, dict[str, list[str]]] = {}
    for kind, files_by_name in _nikad_index().items():
        for filename, nikad in files_by_name.items():
            files = result.setdefault(nikad, {}).setdefault(kind, [])
            files.append(filename)
            resp = response_filename(filename)
            if (XML_DIR / resp).exists():
                files.append(resp)
    return result


def latest_timestamp_for(filenames: list[str]) -> dt.datetime | None:
    """Самая поздняя дата/время среди данного списка имён файлов — для
    сортировки никадов «сначала свежие» без похода в API."""
    timestamps = [
        ts for f in filenames for ts in (filename_timestamp(f),) if ts is not None
    ]
    return max(timestamps) if timestamps else None


_TIMESTAMP_RE = re.compile(r"^(\d{8})_(\d{6})_")


def filename_timestamp(filename: str) -> dt.datetime | None:
    """Дата/время из имени файла (<YYYYMMDD>_<HHMMSS>_...) или None."""
    m = _TIMESTAMP_RE.match(filename)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def latest_local_timestamp() -> dt.datetime | None:
    """Самая поздняя дата/время среди имён всех локальных xml-файлов (любого
    типа) — начало диапазона для синхронизации новых файлов с сервера."""
    if not XML_DIR.exists():
        return None
    timestamps = [
        ts for p in XML_DIR.iterdir() if p.is_file()
        for ts in (filename_timestamp(p.name),) if ts is not None
    ]
    return max(timestamps) if timestamps else None


def all_local_filenames() -> set[str]:
    """Имена всех файлов, уже лежащих в xmls/ — чтобы вычислить недостающие."""
    if not XML_DIR.exists():
        return set()
    return {p.name for p in XML_DIR.iterdir() if p.is_file()}


def save_local(filename: str, content: str) -> None:
    """Сохраняет скачанный файл в xmls/ (создаёт папку при необходимости)."""
    XML_DIR.mkdir(parents=True, exist_ok=True)
    (XML_DIR / filename).write_text(content, encoding="utf-8")


def format_date(value: dt.datetime) -> str:
    """datetime → строка в формате, который ждёт search-by-date-range."""
    return value.strftime(_DATE_FORMAT)


def sync_from_server(
    client: ApiClient, start: dt.datetime, end: dt.datetime | None = None,
) -> dict[str, Any]:
    """Синхронизирует xmls/ с сервером: ищет файлы за [start, end] через
    search-by-date-range, скачивает и сохраняет те, которых у нас ещё нет.

    Возвращает {found, missing, downloaded: [...], errors: {имя: сообщение}}."""
    end = end or dt.datetime.now()
    resp = client.search_test_files_by_date_range(format_date(start), format_date(end))
    remote_files = (resp.get("data") if isinstance(resp, dict) else None) or []

    existing = all_local_filenames()
    missing = [f for f in remote_files if f not in existing]

    downloaded: list[str] = []
    errors: dict[str, str] = {}
    for filename in missing:
        try:
            content = client.download_test_file(filename)
        except ApiError as exc:
            errors[filename] = str(exc)
            continue
        save_local(filename, content)
        downloaded.append(filename)

    if downloaded:
        invalidate_index()

    return {
        "start": start, "end": end,
        "found": len(remote_files), "missing": len(missing),
        "downloaded": downloaded, "errors": errors,
    }
