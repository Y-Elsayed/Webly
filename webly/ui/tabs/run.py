import streamlit as st

from webly.ui.helpers import _index_dir_ready, _results_file_ready
from webly.ui.project import rebuild_pipelines_for_project


def render_run_tab(current_project: str, cfg: dict, manager):
    st.subheader("Run pipeline")
    action = st.radio(
        "Action",
        ["Crawl + Index", "Crawl only", "Index only"],
        index=0,
        horizontal=True,
    )
    mode_map = {
        "Crawl + Index": "both",
        "Crawl only": "crawl_only",
        "Index only": "index_only",
    }
    mode_val = mode_map[action]

    force_crawl = False
    if mode_val in ("both", "crawl_only"):
        force_crawl = st.checkbox(
            "Force re-crawl (ignore existing results.jsonl)",
            value=False,
        )

    c1, c2 = st.columns(2)
    with c1:
        start_clicked = st.button("Start")
    with c2:
        if st.button("Delete project"):
            st.session_state.confirm_delete = current_project

    if start_clicked:
        rebuild_pipelines_for_project(current_project, manager)
        runtime = st.session_state.get("runtime")
        if runtime is None or runtime.ingest_pipeline is None:
            st.warning(
                "Pipeline build failed. Add an OpenAI API key for chat/OpenAI features, "
                "or use a non-OpenAI embedding model for local indexing."
            )
            st.stop()
        progress = st.progress(0)
        status = st.empty()

        def _progress_cb(current, total, url):
            if total and total > 0:
                progress.progress(min(current / total, 1.0))
                status.caption(f"Indexing {current}/{total}: {url}")
            else:
                status.caption(f"Indexing {current}: {url}")

        runtime.ingest_pipeline.progress_callback = _progress_cb
        with st.spinner(f"Running: {action} for {current_project}..."):
            try:
                result = runtime.run_ingest(force_crawl=force_crawl, mode=mode_val)

                if isinstance(result, dict) and result.get("empty_results"):
                    st.warning(
                        "No pages were saved. Possible causes: start URL not within allowed domains, "
                        "robots blocking, patterns too strict, or JS-only pages."
                    )
                    if result.get("disallowed_report_path"):
                        st.caption(f"Debug report saved to: {result['disallowed_report_path']}")
                else:
                    if mode_val in ("both", "index_only"):
                        ok = _index_dir_ready(cfg["index_dir"])
                        if ok:
                            st.success(f"Index ready at: {cfg['index_dir']}")
                        else:
                            st.error("Indexing finished but index files are missing.")
                    else:
                        if _results_file_ready(cfg["output_dir"], cfg["results_file"]):
                            st.success("Crawl complete. Results file ready.")
                        else:
                            st.warning("Crawl finished, but results file is missing or empty.")
            finally:
                st.session_state.show_run_panel = False
                progress.empty()
                status.empty()

    if st.session_state.get("confirm_delete") == current_project:
        st.warning(f"Confirm delete '{current_project}'?")
        dc1, dc2 = st.columns(2)
        with dc1:
            if st.button("Yes, delete"):
                manager.delete_project(current_project)
                st.session_state.confirm_delete = None
                st.session_state.active_project = None
                st.session_state.runtime = None
                st.session_state.ingest_pipeline = None
                st.session_state.query_pipeline = None
                st.session_state.chat_payload = {
                    "title": None,
                    "settings": {"score_threshold": 0.5, "memory_reset_at": 0},
                    "messages": [],
                }
                st.session_state.active_chat = None
                st.rerun()
        with dc2:
            if st.button("Cancel"):
                st.session_state.confirm_delete = None
                st.rerun()
