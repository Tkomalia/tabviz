"""Гейт авторизации Streamlit: форма логина и хранение клиента в session_state."""
from __future__ import annotations

import streamlit as st

from . import config
from .api import ApiClient, ApiError

_CLIENT_KEY = "api_client"


def get_client() -> ApiClient | None:
    return st.session_state.get(_CLIENT_KEY)


def logout() -> None:
    st.session_state.pop(_CLIENT_KEY, None)


def _login_form() -> None:
    st.title("🌿 Tabigat — просмотр реестров")
    st.caption("Введите логин и пароль платформы. Данные хранятся только в текущей сессии.")
    env_keys = list(config.ENVIRONMENTS.keys())
    with st.form("login"):
        env = st.radio(
            "Среда",
            env_keys,
            index=env_keys.index(config.DEFAULT_ENV),
            format_func=lambda k: f"{config.ENVIRONMENTS[k][0]} ({config.ENVIRONMENTS[k][1]})",
            horizontal=True,
        )
        username = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Войти", type="primary")
    if submitted:
        if not username or not password:
            st.warning("Укажите логин и пароль.")
            return
        client = ApiClient(base_url=config.ENVIRONMENTS[env][1])
        try:
            with st.spinner("Авторизация..."):
                client.login(username, password)
        except ApiError as exc:
            st.error(str(exc))
            return
        st.session_state[_CLIENT_KEY] = client
        st.rerun()


def require_login() -> ApiClient:
    """Возвращает авторизованный клиент или показывает форму и останавливает рендер."""
    client = get_client()
    if client and client.is_authenticated:
        return client
    _login_form()
    st.stop()


def account_sidebar(client: ApiClient) -> None:
    """Общий блок аккаунта в сайдбаре: текущая среда и кнопка «Выйти»."""
    with st.sidebar:
        st.markdown("## 🌿 Tabigat")
        st.caption(f"Среда: {client.base_url}")
        if st.button("Выйти", use_container_width=True):
            logout()
            st.rerun()
        st.divider()
