"""Константы и человекочитаемые названия доменов."""
from __future__ import annotations

from pathlib import Path

# Среды: ключ -> (человекочитаемое имя, базовый URL).
ENVIRONMENTS: dict[str, tuple[str, str]] = {
    "test": ("Тест", "https://test-tabigat.gharysh.kz"),
    "prod": ("Прод", "https://tabigat.gov.kz"),
}
DEFAULT_ENV = "test"
BASE_URL = ENVIRONMENTS[DEFAULT_ENV][1]  # дефолт для обратной совместимости

LOGIN_PATH = "/api/v1/auth/main/auth/login"
REFRESH_PATH = "/api/v1/auth/main/auth/refresh-token"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OPENAPI_FILE = DATA_DIR / "openapi.json"
REGISTRIES_FILE = DATA_DIR / "registries.json"
ENTITY_META_CACHE = DATA_DIR / "entity_meta_cache.json"
CUSTOM_FIELDS_FILE = DATA_DIR / "custom_fields.json"

# Пагинация по умолчанию
DEFAULT_LIMIT = 50
LIMIT_OPTIONS = [25, 50, 100, 200, 500]
# (connect, read) в секундах: соединение быстрое, на чтение даём 15с,
# чтобы зависшие на бэкенде эндпоинты падали быстро, а не висели минуту.
REQUEST_TIMEOUT = (10, 15)

# RU-названия доменов (ключ — первый сегмент тега из OpenAPI)
DOMAIN_LABELS: dict[str, str] = {
    "gis": "ГИС / карты",
    "tab-forest": "Лесное хозяйство",
    "tab-animals": "Животный мир",
    "fires": "Пожары",
    "users": "Пользователи и оргструктура",
    "processes": "Процессы",
    "docs": "Документы",
    "events": "События и уведомления",
    "tasks": "Задачи",
    "lists": "Справочники",
    "integrations": "Интеграции",
    "uploads": "Файлы",
    "auth": "Авторизация",
    "public": "Публичные",
    "centrifugo": "Centrifugo",
    "app": "Система",
}


def domain_label(domain: str) -> str:
    return DOMAIN_LABELS.get(domain, domain)
