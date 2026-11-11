"""Tabigat-viz — Streamlit-приложение для просмотра реестров Tabigat API."""
from __future__ import annotations

import streamlit as st

from tabigat import auth, billet, el_integration, processes_el, registry_view

st.set_page_config(page_title="Tabigat — реестры", page_icon="🌿", layout="wide")


def page_registries() -> None:
    client = auth.require_login()
    registry_view.render(client)


def page_billet() -> None:
    client = auth.require_login()
    billet.render(client)


def page_el_integration() -> None:
    client = auth.require_login()
    el_integration.render(client)


def page_processes_el() -> None:
    client = auth.require_login()
    processes_el.render(client)


def main() -> None:
    nav = st.navigation([
        st.Page(page_registries, title="Реестры", icon="📚", default=True),
        st.Page(page_billet, title="Лесорубочный билет", icon="🌲"),
        st.Page(page_el_integration, title="Интеграция с ЕЛ", icon="🔗"),
        st.Page(page_processes_el, title="Процессы с ЕЛ", icon="📮"),
    ])
    nav.run()


if __name__ == "__main__":
    main()
