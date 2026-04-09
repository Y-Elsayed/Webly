import streamlit as st

from webly.storage.storage_manager import StorageManager
from webly.ui.project import load_project_config
from webly.ui.sidebar import render_sidebar
from webly.ui.state import STORAGE_ROOT, _init_state
from webly.ui.styles import inject_styles
from webly.ui.tabs.chat import render_chat_tab
from webly.ui.tabs.overview import render_overview_tab
from webly.ui.tabs.run import render_run_tab
from webly.ui.tabs.settings import render_settings_tab

st.set_page_config(page_title="Webly", layout="wide")
inject_styles()
_init_state()


@st.cache_resource
def _get_manager():
    return StorageManager(STORAGE_ROOT)


manager = _get_manager()
projects = manager.projects.list()

render_sidebar(manager, projects)

if projects and st.session_state.get("active_project"):
    current_project = st.session_state.active_project
    cfg = load_project_config(current_project, manager)

    st.title(f"Webly — {current_project}")
    tabs = st.tabs(["Overview", "Run", "Chat", "Settings"])

    with tabs[0]:
        render_overview_tab(cfg)
    with tabs[1]:
        render_run_tab(current_project, cfg, manager)
    with tabs[2]:
        render_chat_tab(current_project, cfg, manager)
    with tabs[3]:
        render_settings_tab(current_project, cfg, manager)
else:
    st.title("Webly")
    st.info("Create or select a project from the sidebar to get started.")
