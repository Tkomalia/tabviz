"""Страница «Реестры»: выбор домена/реестра и просмотр через render_registry."""
from __future__ import annotations

import streamlit as st

from . import auth, config, registries, tables
from .api import ApiClient


def render(client: ApiClient) -> None:
    auth.account_sidebar(client)

    with st.sidebar:
        try:
            doms = registries.domains()
        except FileNotFoundError as exc:
            st.error(str(exc))
            st.stop()

        domain = st.selectbox("Домен", doms, format_func=config.domain_label)
        items = registries.registries_in(domain)
        registry = st.selectbox(
            "Реестр", items, format_func=lambda r: r["entity"],
        )

    if registry:
        tables.render_registry(client, registry)
    else:
        st.info("Выберите реестр в левой панели.")
