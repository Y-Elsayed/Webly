import os

import streamlit as st

_UI_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(_UI_DIR)
STORAGE_ROOT = os.path.join(APP_DIR, "websites_storage")

EMBEDDER_OPTIONS = {
    "HuggingFace (MiniLM)": "sentence-transformers/all-MiniLM-L6-v2",
    "OpenAI (text-embedding-3-small)": "openai:text-embedding-3-small",
    "OpenAI (text-embedding-3-large)": "openai:text-embedding-3-large",
}


def _init_state():
    defaults = {
        "active_project": None,
        "ingest_pipeline": None,
        "query_pipeline": None,
        "chat_payload": {"title": None, "settings": {"score_threshold": 0.5}, "messages": []},
        "active_chat": None,
        "show_new_project_form": False,
        "rename_chat_open": None,
        "confirm_delete": None,
        "project_selector": None,
        "show_run_panel": False,
        "last_index_ok": None,
        "last_index_msg": "",
        "user_openai_key": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
