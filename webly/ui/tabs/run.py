import json
from pathlib import Path

import streamlit as st

from webly.contracts import CoreError
from webly.crawl.policy import compatibility
from webly.project_config import ProjectConfig
from webly.ui.helpers import _index_dir_ready
from webly.ui.project import rebuild_pipelines_for_project


def render_run_tab(current_project: str, cfg: dict, manager):
    st.subheader("Run pipeline")
    pending_key = f"pending_publication:{current_project}"
    pending = st.session_state.get(pending_key)
    if pending:
        st.warning("This refresh removes sources. The current index remains active until you approve this exact diff.")
        st.json(pending["proposal"])
        if st.button("Approve this refresh", key=f"approve:{current_project}"):
            runtime = st.session_state.get("runtime")
            if runtime:
                try:
                    result = runtime.run_ingest(
                        mode="index_only", run_id=pending["run_id"], approval=pending["proposal"]["approval_token"]
                    )
                    if result.get("status") == "approval_required":
                        st.session_state[pending_key] = result
                        st.warning("The active index changed. Review the new diff before approving.")
                    else:
                        st.session_state.pop(pending_key, None)
                        st.success("Approved refresh published.")
                except Exception as exc:
                    st.error(str(exc))
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
    selected_run = None
    acknowledge_legacy = False
    if mode_val == "index_only":
        root = Path(cfg["output_dir"]) / "core-v2" / "runs"
        completed = []
        for manifest in sorted(root.glob("*/run.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if data.get("status") == "completed":
                    info = compatibility(data, ProjectConfig.from_dict(cfg).to_dict())
                    if info["compatible"]:
                        completed.append(data["run_id"])
                    else:
                        st.caption(f"Run {data['run_id']} requires a fresh crawl under the current source policy.")
            except (CoreError, ValueError, OSError, KeyError):
                continue
        selected_run = st.selectbox("Completed crawl run", completed) if completed else None
        if not completed:
            st.caption("Existing 0.1 HTML can be imported into a new Core 0.2 run. Old indexes remain untouched.")
            acknowledge_legacy = st.checkbox("I confirm the legacy crawl is complete and approve importing it")

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
                if mode_val == "index_only" and not selected_run:
                    if not acknowledge_legacy:
                        raise ValueError("Choose a completed run or explicitly confirm the legacy import")
                    selected_run = runtime.import_legacy(
                        Path(cfg["output_dir"]) / cfg["results_file"], acknowledge_complete=True
                    )
                result = runtime.run_ingest(
                    force_crawl=force_crawl, mode=mode_val, **({"run_id": selected_run} if selected_run else {})
                )
                if result.get("status") == "approval_required":
                    st.session_state[pending_key] = result
                    st.warning("Review the pending source-removal diff above before publishing.")
                    return
                if result.get("run_id"):
                    st.caption(f"Crawl run: {result['run_id']}")

                summary = result.get("ingest_summary") or {}
                if summary:
                    st.caption(
                        f"Pages processed: {summary['pages_total']} · "
                        f"Indexed: {summary['pages_indexed']} · "
                        f"Skipped: {summary['pages_skipped']} · "
                        f"Duplicates merged: {summary['duplicate_pages']} · "
                        f"Segments indexed: {summary['segments_indexed']}"
                    )
                    if summary["pages_skipped"]:
                        st.warning(
                            f"Skipped {summary['pages_skipped']} pages with no extractable content. "
                            "The remaining pages were indexed. Review the ingestion report for skipped URLs."
                        )
                    if result.get("ingest_report_path"):
                        st.caption(f"Ingestion report: {result['ingest_report_path']}")

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
                        if result.get("run_id"):
                            st.success("Crawl complete. Results file ready.")
                        else:
                            st.warning("Crawl finished, but results file is missing or empty.")
            except Exception as exc:
                st.error(str(exc))
                if getattr(runtime.ingest_pipeline, "_report_written", False):
                    st.caption(f"Ingestion report: {runtime.ingest_pipeline.ingest_report_path}")
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
