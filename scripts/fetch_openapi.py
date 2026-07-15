"""Скачивает OpenAPI-спецификацию Tabigat и строит каталог реестров.

Спецификация встроена в `swagger-ui-init.js` как объект `swaggerDoc`, поэтому
обычным GET /openapi.json её не достать — извлекаем из JS сопоставлением скобок.

Запуск:
    python scripts/fetch_openapi.py
Результат:
    data/openapi.json     — полная спецификация
    data/registries.json  — список list-эндпоинтов ("Retrieve multiple ...")
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

INIT_JS_URL = "https://tabigat.gov.kz/apidocs/swagger-ui-init.js"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def extract_swagger_doc(js: str) -> dict:
    """Достаёт JSON-объект, следующий за ключом "swaggerDoc", балансом скобок."""
    marker = '"swaggerDoc":'
    i = js.find(marker)
    if i == -1:
        raise ValueError('Не найден ключ "swaggerDoc" в swagger-ui-init.js')
    start = js.index("{", i + len(marker))
    depth = 0
    for j in range(start, len(js)):
        ch = js[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(js[start : j + 1])
    raise ValueError("Не удалось сбалансировать скобки объекта swaggerDoc")


def build_registry_catalog(spec: dict) -> list[dict]:
    """List-эндпоинты crud ('Retrieve multiple ...'), у которых есть entity-meta.

    Работаем только с моделями, имеющими метод {path}/entity-meta — модели без
    него не показываем (см. требования к UI).
    """
    paths = spec.get("paths", {})
    catalog: list[dict] = []
    for path, methods in paths.items():
        get = methods.get("get")
        if not get:
            continue
        summary = get.get("summary") or ""
        if "Retrieve multiple" not in summary:
            continue
        if f"{path}/entity-meta" not in paths:
            continue
        tags = get.get("tags") or [""]
        tag = tags[0]
        # тег вида "tab-forest: main: forest-ticket"
        domain = tag.split(":")[0].strip() if ":" in tag else tag.strip()
        # entity = последний непустой сегмент пути
        segs = [s for s in path.strip("/").split("/") if s]
        entity = segs[-1] if segs else path
        catalog.append(
            {
                "path": path,
                "tag": tag,
                "domain": domain,
                "entity": entity,
                "summary": summary,
            }
        )
    catalog.sort(key=lambda r: (r["domain"], r["entity"]))
    return catalog


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Скачиваю {INIT_JS_URL} ...")
    resp = requests.get(INIT_JS_URL, timeout=60)
    resp.raise_for_status()
    spec = extract_swagger_doc(resp.text)

    openapi_path = DATA_DIR / "openapi.json"
    openapi_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    n_paths = len(spec.get("paths", {}))
    print(f"  сохранено: {openapi_path} ({n_paths} путей)")

    catalog = build_registry_catalog(spec)
    registries_path = DATA_DIR / "registries.json"
    registries_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  сохранено: {registries_path} ({len(catalog)} реестров)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
