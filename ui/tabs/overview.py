import streamlit as st

from ui.helpers import _index_dir_ready, _results_file_ready


def render_overview_tab(cfg: dict):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Start URL", cfg.get("start_url", ""))
    with col2:
        st.metric("Embedding", cfg.get("embedding_model", ""))
    with col3:
        st.metric("Chat model", cfg.get("chat_model", ""))

    ready_idx = _index_dir_ready(cfg["index_dir"])
    ready_res = _results_file_ready(cfg["output_dir"], cfg["results_file"])
    status = "Ready" if (ready_idx and ready_res) else "Not ready"
    st.info(f"Pipeline status: {status}")

    st.write("Use the Run tab to crawl and index. Use Chat to ask questions.")
