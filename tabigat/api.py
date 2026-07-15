"""HTTP-клиент к Tabigat API: логин, обновление токена, чтение реестров."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from . import config

logger = logging.getLogger("tabigat.api")
if not logger.handlers:
    _h = logging.StreamHandler()  # stderr → виден в терминале Streamlit
    _h.setFormatter(logging.Formatter("[api] %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)
    logger.propagate = False

# Вероятные имена полей токенов в ответе логина (схема в OpenAPI — generic object).
_ACCESS_KEYS = ("accessToken", "access_token", "token", "jwt", "access")
_REFRESH_KEYS = ("refreshToken", "refresh_token", "refresh")


class ApiError(Exception):
    """Ошибка обращения к API с человекочитаемым сообщением."""


def _find_token(payload: Any, keys: tuple[str, ...]) -> str | None:
    """Ищет токен по списку ключей, в т.ч. внутри вложенных dict.

    Поддерживает как плоскую форму ({"access_token": "..."}), так и
    вложенную ({"tokens": {"access": {"token": "..."}}}): если значение
    ключа из списка — dict, ищем в нём поле token.
    """
    if not isinstance(payload, dict):
        return None
    for k in keys:
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, dict):
            inner = v.get("token")
            if isinstance(inner, str) and inner:
                return inner
    for nested in ("data", "tokens", "result", "payload"):
        if isinstance(payload.get(nested), dict):
            found = _find_token(payload[nested], keys)
            if found:
                return found
    return None


class ApiClient:
    """Тонкая обёртка над requests.Session с авто-refresh при 401."""

    def __init__(self, base_url: str = config.BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.access_token: str | None = None
        self.refresh_token: str | None = None

    def _send(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Единая точка HTTP-запросов с логированием метода/URL/статуса/времени."""
        kwargs.setdefault("timeout", config.REQUEST_TIMEOUT)
        started = time.perf_counter()
        logger.info("%s %s ...", method, url)
        try:
            resp = self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            elapsed = time.perf_counter() - started
            logger.warning("%s %s -> ОШИБКА за %.1fс: %s", method, url, elapsed, exc)
            raise
        elapsed = time.perf_counter() - started
        logger.info("%s %s -> %s за %.2fс", method, url, resp.status_code, elapsed)
        return resp

    # --- авторизация -----------------------------------------------------
    def login(self, username: str, password: str) -> None:
        url = self.base_url + config.LOGIN_PATH
        try:
            resp = self._send(
                "POST", url,
                json={"username": username, "password": password},
                headers={"accept": "application/json"},
            )
        except requests.RequestException as exc:
            raise ApiError(f"Сеть недоступна: {exc}") from exc

        if resp.status_code == 401:
            raise ApiError("Неверный логин или пароль.")
        if resp.status_code >= 400:
            raise ApiError(f"Ошибка логина ({resp.status_code}): {resp.text[:300]}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise ApiError("Сервер вернул не-JSON при логине.") from exc

        access = _find_token(data, _ACCESS_KEYS)
        if not access:
            raise ApiError(
                "Не удалось найти access-токен в ответе. Поля ответа: "
                + ", ".join(map(str, data.keys() if isinstance(data, dict) else []))
            )
        self.access_token = access
        self.refresh_token = _find_token(data, _REFRESH_KEYS)

    def _do_refresh(self) -> bool:
        if not self.refresh_token:
            return False
        url = self.base_url + config.REFRESH_PATH
        try:
            resp = self._send(
                "POST", url,
                json={"refreshToken": self.refresh_token},
                headers={"accept": "application/json"},
            )
        except requests.RequestException:
            return False
        if resp.status_code >= 400:
            return False
        try:
            data = resp.json()
        except ValueError:
            return False
        access = _find_token(data, _ACCESS_KEYS)
        if not access:
            return False
        self.access_token = access
        new_refresh = _find_token(data, _REFRESH_KEYS)
        if new_refresh:
            self.refresh_token = new_refresh
        return True

    @property
    def is_authenticated(self) -> bool:
        return bool(self.access_token)

    # --- запросы ---------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    def _get(self, path: str, params: dict[str, Any] | None = None) -> requests.Response:
        url = self.base_url + path
        resp = self._send("GET", url, params=params, headers=self._headers())
        if resp.status_code == 401 and self._do_refresh():
            resp = self._send("GET", url, params=params, headers=self._headers())
        return resp

    def _patch(self, path: str, body: dict[str, Any]) -> requests.Response:
        url = self.base_url + path
        resp = self._send("PATCH", url, json=body, headers=self._headers())
        if resp.status_code == 401 and self._do_refresh():
            resp = self._send("PATCH", url, json=body, headers=self._headers())
        return resp

    def get_many(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Возвращает нормализованный ответ get-many: {data, total, page, count, pageCount}."""
        try:
            resp = self._get(path, params)
        except requests.RequestException as exc:
            raise ApiError(f"Сеть недоступна: {exc}") from exc
        if resp.status_code == 401:
            raise ApiError("Сессия истекла, войдите заново.")
        if resp.status_code >= 400:
            raise ApiError(f"Ошибка запроса ({resp.status_code}): {resp.text[:300]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise ApiError("Сервер вернул не-JSON.") from exc

        # crud может вернуть либо {data,...}, либо просто массив
        if isinstance(data, list):
            return {
                "data": data,
                "total": len(data),
                "count": len(data),
                "page": 1,
                "pageCount": 1,
            }
        if isinstance(data, dict) and "data" in data:
            return data
        return {"data": [data], "total": 1, "count": 1, "page": 1, "pageCount": 1}

    def entity_meta(self, path: str) -> Any:
        """GET {path}/entity-meta — список полей (колонок) сущности.

        Бросает ApiError при сетевом сбое или статусе >=400, чтобы причина
        (например Kafka-500) была видна пользователю.
        """
        try:
            resp = self._get(path.rstrip("/") + "/entity-meta")
        except requests.RequestException as exc:
            raise ApiError(f"Сеть недоступна: {exc}") from exc
        if resp.status_code == 401:
            raise ApiError("Сессия истекла, войдите заново.")
        if resp.status_code >= 400:
            raise ApiError(
                f"Ошибка entity-meta ({resp.status_code}): {resp.text[:300]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise ApiError("Сервер вернул не-JSON для entity-meta.") from exc

    def get_one(self, path: str, record_id: Any) -> Any:
        try:
            resp = self._get(f"{path.rstrip('/')}/{record_id}")
        except requests.RequestException as exc:
            raise ApiError(f"Сеть недоступна: {exc}") from exc
        if resp.status_code >= 400:
            raise ApiError(f"Ошибка запроса ({resp.status_code}): {resp.text[:300]}")
        return resp.json()

    def update(self, path: str, record_id: Any, body: dict[str, Any]) -> Any:
        """PATCH {path}/{record_id} — частичное обновление записи (nestjsx/crud)."""
        try:
            resp = self._patch(f"{path.rstrip('/')}/{record_id}", body)
        except requests.RequestException as exc:
            raise ApiError(f"Сеть недоступна: {exc}") from exc
        if resp.status_code == 401:
            raise ApiError("Сессия истекла, войдите заново.")
        if resp.status_code >= 400:
            raise ApiError(f"Ошибка обновления ({resp.status_code}): {resp.text[:300]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise ApiError("Сервер вернул не-JSON.") from exc
