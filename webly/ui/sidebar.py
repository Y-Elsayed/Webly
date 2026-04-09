import streamlit as st

from webly.chatbot.prompts.system_prompts import AnsweringMode
from webly.ui.helpers import (
    _index_dir_ready,
    _mask_key,
    _results_file_ready,
    _validate_openai_key,
)
from webly.ui.project import (
    ensure_project_pipelines,
    load_project_config,
    rebuild_pipelines_for_project,
)
from webly.ui.state import EMBEDDER_OPTIONS


def render_sidebar(manager, projects: list) -> str | None:
    project_repo = manager.projects

    with st.sidebar:
        st.title("Webly")
        st.caption("Website to searchable knowledge base")

        # ---- OpenAI key ----
        st.subheader("OpenAI")
        current = st.session_state.get("user_openai_key")
        if current:
            st.success(f"Connected: {_mask_key(current)}")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Forget key"):
                    st.session_state.user_openai_key = None
                    st.success("Key removed from this session.")
            with col_b:
                if st.button("Rebuild pipelines"):
                    if st.session_state.get("active_project"):
                        proj = st.session_state.active_project
                        rebuild_pipelines_for_project(proj, manager, api_key=current)
                        st.success("Pipelines rebuilt.")
        else:
            k = st.text_input(
                "Paste API key",
                type="password",
                placeholder="sk-...",
                help="Stored in memory for this session only.",
            )
            if st.button("Connect"):
                ok, err = _validate_openai_key(k.strip())
                if ok:
                    st.session_state.user_openai_key = k.strip()
                    st.success("Connected. Your key is kept only in this session.")
                else:
                    st.error(err or "Could not validate key.")

        st.divider()

        # ---- Projects ----
        st.subheader("Projects")
        if st.button("New project"):
            st.session_state.show_new_project_form = True

        if st.session_state.get("show_new_project_form", False):
            with st.expander("Create new project", expanded=True):
                new_name = st.text_input("Project name", key="new_project_name")
                new_url = st.text_input("Start URL", key="new_project_url")
                new_domains = st.text_area(
                    "Allowed domains (comma-separated)", key="new_project_domains"
                )
                embed_choice = st.selectbox(
                    "Embedding model", list(EMBEDDER_OPTIONS.keys()), key="new_embed_choice"
                )

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Create", key="create_project_btn"):
                        if not new_name.strip():
                            st.error("Project name is required.")
                        elif not new_url.strip().startswith(("http://", "https://")):
                            st.error("Start URL must begin with http:// or https://")
                        else:
                            cfg = {
                                "start_url": new_url,
                                "allowed_domains": [
                                    d.strip() for d in new_domains.split(",") if d.strip()
                                ],
                                "embedding_model": EMBEDDER_OPTIONS[embed_choice],
                                "chat_model": "gpt-4o-mini",
                                "answering_mode": AnsweringMode.TECHNICAL_GROUNDED.value,
                                "allow_generated_examples": False,
                                "system_prompt_custom_override": False,
                                "system_prompt": "",
                                "summary_model": "",
                                "score_threshold": 0.5,
                                "retrieval_mode": "builder",
                                "builder_max_rounds": 1,
                                "leave_last_k": 2,
                                "crawl_entire_site": True,
                                "results_file": "results.jsonl",
                                "allow_subdomains": False,
                                "respect_robots": True,
                                "max_depth": 3,
                                "rate_limit_delay": 0.2,
                                "allowed_paths": [],
                                "blocked_paths": [],
                                "allow_url_patterns": [],
                                "block_url_patterns": [],
                                "seed_urls": [],
                            }
                            try:
                                project_repo.create(new_name, cfg)
                                st.session_state.show_new_project_form = False
                                st.session_state.project_selector = new_name
                                rebuild_pipelines_for_project(new_name, manager)
                                st.rerun()
                            except ValueError as e:
                                st.error(f"Invalid project name: {e}")
                with col2:
                    if st.button("Cancel", key="cancel_project_btn"):
                        st.session_state.show_new_project_form = False

        if projects:
            default_index = 0
            if st.session_state.active_project in projects:
                default_index = projects.index(st.session_state.active_project)
            selected = st.selectbox(
                "Select project",
                projects,
                index=default_index,
                key="project_selector",
            )
        else:
            selected = st.selectbox("Select project", ["No projects yet"])

        if projects and selected not in (None, "No projects yet"):
            cfg = load_project_config(selected, manager)
            ensure_project_pipelines(selected, manager)

            ready_idx = _index_dir_ready(cfg["index_dir"])
            ready_res = _results_file_ready(cfg["output_dir"], cfg["results_file"])
            st.caption(
                f"Results: {'Ready' if ready_res else 'Missing'}  |  "
                f"Index: {'Ready' if ready_idx else 'Missing'}"
            )

    return selected
