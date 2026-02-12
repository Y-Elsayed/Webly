import os
from urllib.parse import urlparse

import streamlit as st
from openai import OpenAI

from main import build_pipelines
from storage.storage_manager import StorageManager

# ------------------------------------------------------------------------------------
# Paths & imports
# ------------------------------------------------------------------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_ROOT = os.path.join(APP_DIR, "websites_storage")

# ------------------------------------------------------------------------------------
# Page
# ------------------------------------------------------------------------------------
st.set_page_config(page_title="Webly", layout="wide")
st.markdown(
    """
    <style>
    /* Pin default Streamlit chat input without changing its look */
    div[data-testid="stChatInput"] {
        position: fixed;
        bottom: 0;
        left: 50%;
        transform: translateX(-50%);
        width: var(--content-width, 700px);
        max-width: 90vw;
        z-index: 1000;
        background: transparent;
    }
    /* Prevent messages from being hidden behind the input */
    .stMainBlockContainer {
        padding-bottom: 7.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------------------------
# Session State
# ------------------------------------------------------------------------------------


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


_init_state()

# ------------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------------

EMBEDDER_OPTIONS = {
    "HuggingFace (MiniLM)": "sentence-transformers/all-MiniLM-L6-v2",
    "OpenAI (text-embedding-3-small)": "openai:text-embedding-3-small",
    "OpenAI (text-embedding-3-large)": "openai:text-embedding-3-large",
}

# ------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------


def _mask_key(k: str) -> str:
    if not k or len(k) < 8:
        return "****"
    return f"{k[:3]}********{k[-4:]}"


def _validate_openai_key(k: str) -> tuple[bool, str | None]:
    try:
        client = OpenAI(api_key=k)
        _ = client.models.list()
        return True, None
    except Exception as e:
        msg = str(e)
        if "api_key" in msg.lower():
            msg = "Invalid or unauthorized key."
        return False, msg


def _index_dir_ready(index_dir: str) -> bool:
    if not index_dir or not os.path.isdir(index_dir):
        return False
    try:
        files = os.listdir(index_dir)
    except Exception:
        return False
    has_index = any(f.lower().endswith(".index") for f in files)
    has_meta = any(f.lower().startswith("metadata") for f in files)
    return has_index and has_meta


def _domain_from_url(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.strip().lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc.split(":")[0]
    except Exception:
        return ""


def _results_file_ready(output_dir: str, results_file: str) -> bool:
    path = os.path.join(output_dir, results_file)
    return os.path.exists(path) and os.path.getsize(path) > 0


# ------------------------------------------------------------------------------------
# Storage / Projects
# ------------------------------------------------------------------------------------

manager = StorageManager(STORAGE_ROOT)
projects = manager.list_projects()


# ------------------------------------------------------------------------------------
# Config helpers
# ------------------------------------------------------------------------------------


def load_project_config(project: str) -> dict:
    cfg = manager.get_config(project)
    paths = manager.get_paths(project)
    root = os.path.join(STORAGE_ROOT, project) if not os.path.isabs(paths["root"]) else paths["root"]
    index_dir = os.path.join(root, "index")
    cfg["output_dir"] = root
    cfg["index_dir"] = index_dir
    cfg["results_file"] = cfg.get("results_file", "results.jsonl")
    return cfg


def ensure_chat_payload_shape(payload):
    if isinstance(payload, list):
        msgs = []
        for item in payload:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                msgs.append({"role": "user", "content": item[0]})
                msgs.append({"role": "assistant", "content": item[1]})
        return {"title": "Imported Chat", "settings": {"score_threshold": 0.5}, "messages": msgs}
    payload.setdefault("title", "Untitled Chat")
    payload.setdefault("settings", {"score_threshold": 0.5})
    payload.setdefault("messages", [])
    payload["settings"].setdefault("score_threshold", 0.5)
    return payload


def build_memory_context(messages, max_chars: int = 2000) -> str:
    """
    Build a compact memory string from the most recent chat messages.
    Includes roles and truncates to a character budget.
    """
    if not messages:
        return ""
    buf = []
    total = 0
    # Walk backwards, then reverse for chronological order
    for msg in reversed(messages):
        role = msg.get("role", "user")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        line = f"{role.title()}: {content}"
        if total + len(line) + 1 > max_chars:
            break
        buf.append(line)
        total += len(line) + 1
    return "\n".join(reversed(buf)).strip()


def rebuild_pipelines_for_project(project: str, api_key: str | None = None):
    if not project or project == "No projects yet":
        return
    cfg = load_project_config(project)
    os.makedirs(cfg["output_dir"], exist_ok=True)
    os.makedirs(cfg["index_dir"], exist_ok=True)
    key = api_key or st.session_state.get("user_openai_key")
    try:
        st.session_state.ingest_pipeline, st.session_state.query_pipeline = build_pipelines(cfg, api_key=key)
    except RuntimeError as e:
        st.session_state.ingest_pipeline = None
        st.session_state.query_pipeline = None
        st.warning(str(e))
        return
    st.session_state.missing_key_notice = not bool(key)
    st.session_state.active_project = project
    st.session_state.active_chat = None
    st.session_state.chat_payload = {
        "title": None,
        "settings": {"score_threshold": float(cfg.get("score_threshold", 0.5))},
        "messages": [],
    }


def ensure_project_pipelines(selected_project: str):
    has_key = bool(st.session_state.get("user_openai_key"))
    if (
        ("active_project" not in st.session_state)
        or (st.session_state.active_project != selected_project)
        or (st.session_state.ingest_pipeline is None)
        or (has_key and st.session_state.query_pipeline is None)
    ):
        rebuild_pipelines_for_project(
            selected_project,
            api_key=st.session_state.get("user_openai_key"),
        )


# ------------------------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------------------------

with st.sidebar:
    st.title("Webly")
    st.caption("Website to searchable knowledge base")

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
                    rebuild_pipelines_for_project(proj, api_key=current)
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

    st.subheader("Projects")
    if st.button("New project"):
        st.session_state.show_new_project_form = True

    if st.session_state.get("show_new_project_form", False):
        with st.expander("Create new project", expanded=True):
            new_name = st.text_input("Project name", key="new_project_name")
            new_url = st.text_input("Start URL", key="new_project_url")
            new_domains = st.text_area("Allowed domains (comma-separated)", key="new_project_domains")
            embed_choice = st.selectbox("Embedding model", list(EMBEDDER_OPTIONS.keys()), key="new_embed_choice")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Create", key="create_project_btn"):
                    cfg = {
                        "start_url": new_url,
                        "allowed_domains": [d.strip() for d in new_domains.split(",") if d.strip()],
                        "embedding_model": EMBEDDER_OPTIONS[embed_choice],
                        "chat_model": "gpt-4o-mini",
                        "summary_model": "",
                        "score_threshold": 0.5,
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
                    root = os.path.join(STORAGE_ROOT, new_name)
                    index_dir = os.path.join(root, "index")
                    os.makedirs(index_dir, exist_ok=True)
                    cfg["output_dir"] = root
                    cfg["index_dir"] = index_dir
                    manager.create_project(new_name, cfg)
                    st.session_state.show_new_project_form = False
                    st.session_state.project_selector = new_name
                    rebuild_pipelines_for_project(new_name)
                    st.rerun()
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
        cfg = load_project_config(selected)
        ensure_project_pipelines(selected)

        ready_idx = _index_dir_ready(cfg["index_dir"])
        ready_res = _results_file_ready(cfg["output_dir"], cfg["results_file"])
        st.caption(
            f"Results: {'Ready' if ready_res else 'Missing'}  |  " f"Index: {'Ready' if ready_idx else 'Missing'}"
        )


# ------------------------------------------------------------------------------------
# Main layout
# ------------------------------------------------------------------------------------

if projects and st.session_state.get("active_project"):
    current_project = st.session_state.active_project
    cfg = load_project_config(current_project)

    st.title(f"Webly — {current_project}")

    tabs = st.tabs(["Overview", "Run", "Chat", "Settings"])

    # -------------------- Overview --------------------
    with tabs[0]:
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

    # -------------------- Run --------------------
    with tabs[1]:
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
            rebuild_pipelines_for_project(current_project)
            if st.session_state.ingest_pipeline is None:
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

            st.session_state.ingest_pipeline.progress_callback = _progress_cb
            with st.spinner(f"Running: {action} for {current_project}..."):
                try:
                    result = st.session_state.ingest_pipeline.run(force_crawl=force_crawl, mode=mode_val)

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
                    st.session_state.ingest_pipeline = None
                    st.session_state.query_pipeline = None
                    st.session_state.chat_payload = {
                        "title": None,
                        "settings": {"score_threshold": 0.5},
                        "messages": [],
                    }
                    st.session_state.active_chat = None
                    st.rerun()
            with dc2:
                if st.button("Cancel"):
                    st.session_state.confirm_delete = None
                    st.rerun()

    # -------------------- Chat --------------------
    with tabs[2]:
        chats = manager.list_chats(current_project)
        active = st.session_state.get("active_chat")

        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.subheader("Chats")
        with col_b:
            if st.button("New chat"):
                base, idx = "Chat", 1
                new_name = f"{base} {idx}"
                while new_name in chats:
                    idx += 1
                    new_name = f"{base} {idx}"
                st.session_state.active_chat = new_name
                st.session_state.chat_payload = {
                    "title": new_name,
                    "settings": {"score_threshold": cfg.get("score_threshold", 0.5)},
                    "messages": [],
                }
                manager.save_chat(current_project, new_name, st.session_state.chat_payload)
                st.rerun()

        for chat_name in chats:
            is_active = chat_name == active
            label = f"{chat_name}" + (" (active)" if is_active else "")
            c1, c2, c3 = st.columns([4, 1, 1])
            with c1:
                if st.button(label, key=f"sel_{chat_name}"):
                    st.session_state.active_chat = chat_name
                    payload = manager.load_chat(current_project, chat_name)
                    st.session_state.chat_payload = ensure_chat_payload_shape(payload)
                    st.rerun()
            with c2:
                if st.button("Clear memory", key=f"clear_{chat_name}"):
                    if st.session_state.get("active_chat") == chat_name:
                        st.session_state.chat_payload = {
                            "title": chat_name,
                            "settings": {"score_threshold": cfg.get("score_threshold", 0.5)},
                            "messages": [],
                        }
                        manager.save_chat(current_project, chat_name, st.session_state.chat_payload)
                    else:
                        # Clear memory even if not active
                        payload = manager.load_chat(current_project, chat_name)
                        payload = ensure_chat_payload_shape(payload)
                        payload["messages"] = []
                        manager.save_chat(current_project, chat_name, payload)
                    st.rerun()
            with c3:
                if st.button("Delete", key=f"del_{chat_name}"):
                    manager.delete_chat(current_project, chat_name)
                    if st.session_state.get("active_chat") == chat_name:
                        st.session_state.active_chat = None
                        st.session_state.chat_payload = {
                            "title": None,
                            "settings": {"score_threshold": 0.5},
                            "messages": [],
                        }
                    st.rerun()

        st.divider()

        payload = ensure_chat_payload_shape(st.session_state.get("chat_payload", {"messages": []}))
        for msg in payload["messages"]:
            st.chat_message(msg["role"]).write(msg["content"])

        if st.session_state.get("active_chat"):
            user_input = st.chat_input("Message Webly...")
            if user_input:
                # Show user message immediately
                st.chat_message("user").write(user_input)
                payload["messages"].append({"role": "user", "content": user_input})
                ensure_project_pipelines(current_project)
                cfg_cur = load_project_config(current_project)

                if st.session_state.query_pipeline is None:
                    assistant_reply = "Please add your OpenAI API key in the sidebar to enable chat."
                elif not _index_dir_ready(cfg_cur["index_dir"]):
                    assistant_reply = "No index found. Please run indexing first in the Run tab."
                else:
                    db = st.session_state.ingest_pipeline.db
                    if getattr(db, "index", None) is None:
                        try:
                            db.load(cfg_cur["index_dir"])
                        except Exception as e:
                            assistant_reply = f"Failed to load index: {e}"
                        else:
                            try:
                                memory_ctx = build_memory_context(payload["messages"][:-1], max_chars=2000)
                                assistant_reply = st.session_state.query_pipeline.query(
                                    user_input, memory_context=memory_ctx
                                )
                            except Exception as e:
                                assistant_reply = f"Query failed: {e}"
                    else:
                        try:
                            memory_ctx = build_memory_context(payload["messages"][:-1], max_chars=2000)
                            assistant_reply = st.session_state.query_pipeline.query(
                                user_input, memory_context=memory_ctx
                            )
                        except Exception as e:
                            assistant_reply = f"Query failed: {e}"

                payload["messages"].append({"role": "assistant", "content": assistant_reply})
                st.session_state.chat_payload = payload
                manager.save_chat(current_project, st.session_state.active_chat, payload)
                st.chat_message("assistant").write(assistant_reply)
        else:
            st.info("Create or select a chat to start.")

    # -------------------- Settings --------------------
    with tabs[3]:
        st.subheader("Project settings")
        crawl_tab, index_tab, chat_tab = st.tabs(["Crawling", "Indexing", "Chat"])

        with crawl_tab:
            start_url_input = st.text_input(
                "Start URL",
                cfg.get("start_url", ""),
                placeholder="https://example.com/docs",
                help="Example: https://example.com/docs",
            )

            allowed_domains_text = ", ".join(cfg.get("allowed_domains", []))
            allowed_domains_input = st.text_area(
                "Allowed domains (comma-separated)",
                allowed_domains_text,
                placeholder="example.com, docs.example.com",
                help="If left empty and you choose Entire site, Webly auto-fills from Start URL.",
            )
            st.caption("Format: domain list, comma-separated. Example: `example.com, docs.example.com`")

            crawl_mode = st.radio(
                "Crawl scope",
                ["Entire site", "Only URLs matching patterns", "Only specific pages"],
                index=0 if cfg.get("crawl_entire_site", True) else (2 if cfg.get("seed_urls") else 1),
            )

            allowed_paths_text = st.text_area(
                "Allowed paths (prefixes, comma-separated)",
                ", ".join(cfg.get("allowed_paths", [])),
                placeholder="/docs, /blog",
                help="Example: /docs, /blog",
            )
            st.caption("Path prefix format: start with `/`. Example: `/docs, /blog`")
            blocked_paths_text = st.text_area(
                "Blocked paths (prefixes, comma-separated)",
                ", ".join(cfg.get("blocked_paths", [])),
                placeholder="/login, /checkout",
                help="Example: /login, /checkout",
            )
            st.caption("Blocked prefix format: start with `/`. Example: `/login, /checkout`")
            allow_patterns_text = st.text_area(
                "Allow URL patterns (regex, one per line)",
                "\n".join(cfg.get("allow_url_patterns", [])),
                placeholder="^https://example\\.com/docs/.*$",
                help="Example regex per line.",
            )
            st.caption(
                "Regex format: one pattern per line. Example: "
                "`^https://example\\.com/docs/.*$`"
            )
            block_patterns_text = st.text_area(
                "Block URL patterns (regex, one per line)",
                "\n".join(cfg.get("block_url_patterns", [])),
                placeholder=".*\\?(utm_|ref=).*",
                help="Example regex per line.",
            )
            st.caption(
                "Regex format: one pattern per line. Example: "
                "`.*\\?(utm_|ref=).*`"
            )

            seed_urls_text = st.text_area(
                "Specific pages (one URL per line)",
                "\n".join(cfg.get("seed_urls", [])),
                placeholder="https://example.com/docs/getting-started\nhttps://example.com/docs/api",
                help="Used only when 'Only specific pages' is selected.",
            )
            st.caption(
                "One full URL per line. Example:\n"
                "`https://example.com/docs/getting-started`\n"
                "`https://example.com/docs/api`"
            )

            allow_subdomains = st.checkbox("Allow subdomains", value=cfg.get("allow_subdomains", False))
            respect_robots = st.checkbox("Respect robots.txt", value=cfg.get("respect_robots", True))

            no_depth_limit = st.checkbox(
                "No depth limit",
                value=(cfg.get("max_depth", 3) in (-1, None)),
            )
            if no_depth_limit:
                max_depth_val = -1
            else:
                max_depth_val = st.number_input(
                    "Max depth", min_value=0, max_value=20, value=int(cfg.get("max_depth", 3))
                )

            rate_limit_delay = st.number_input(
                "Rate limit delay (seconds between requests)",
                min_value=0.0,
                max_value=5.0,
                value=float(cfg.get("rate_limit_delay", 0.2)),
                step=0.1,
            )

        with index_tab:
            reverse_map = {v: k for k, v in EMBEDDER_OPTIONS.items()}
            current_embed_choice = reverse_map.get(cfg.get("embedding_model"), "HuggingFace (MiniLM)")
            embed_choice = st.selectbox(
                "Embedding model",
                list(EMBEDDER_OPTIONS.keys()),
                index=list(EMBEDDER_OPTIONS.keys()).index(current_embed_choice),
            )
            results_file_input = st.text_input(
                "Results file (advanced)",
                cfg.get("results_file", "results.jsonl"),
                placeholder="results.jsonl",
                help="Example: results.jsonl",
            )

        with chat_tab:
            chat_model = st.text_input(
                "Chat model",
                cfg.get("chat_model", "gpt-4o-mini"),
                placeholder="gpt-4o-mini",
                help="Example: gpt-4o-mini",
            )
            summary_model = st.text_input(
                "Summary model (optional)",
                cfg.get("summary_model", ""),
                placeholder="gpt-4o-mini",
                help="Optional. Example: gpt-4o-mini",
            )
            score_threshold = st.slider(
                "Default similarity threshold",
                0.0,
                1.0,
                float(cfg.get("score_threshold", 0.5)),
            )

        if st.button("Save settings"):
            if isinstance(allowed_domains_input, str):
                ad_list = [d.strip() for d in allowed_domains_input.split(",") if d.strip()]
            else:
                ad_list = allowed_domains_input

            auto_msg = ""
            if (crawl_mode == "Entire site") and not ad_list:
                dom = _domain_from_url(start_url_input)
                if dom:
                    ad_list = [dom]
                    auto_msg = f"Allowed domains was empty; auto-set to [{dom}] based on Start URL."
                else:
                    auto_msg = "Start URL missing/invalid; could not auto-set Allowed Domains."

            cfg_edit = cfg.copy()
            cfg_edit["start_url"] = start_url_input
            cfg_edit["allowed_domains"] = ad_list
            cfg_edit["allowed_paths"] = [p.strip() for p in allowed_paths_text.split(",") if p.strip()]
            cfg_edit["blocked_paths"] = [p.strip() for p in blocked_paths_text.split(",") if p.strip()]
            cfg_edit["allow_url_patterns"] = [p.strip() for p in allow_patterns_text.splitlines() if p.strip()]
            cfg_edit["block_url_patterns"] = [p.strip() for p in block_patterns_text.splitlines() if p.strip()]
            cfg_edit["allow_subdomains"] = bool(allow_subdomains)
            cfg_edit["respect_robots"] = bool(respect_robots)
            cfg_edit["max_depth"] = int(max_depth_val)
            cfg_edit["rate_limit_delay"] = float(rate_limit_delay)

            if crawl_mode == "Entire site":
                cfg_edit["crawl_entire_site"] = True
                cfg_edit["seed_urls"] = []
            elif crawl_mode == "Only URLs matching patterns":
                cfg_edit["crawl_entire_site"] = False
                cfg_edit["seed_urls"] = []
            else:
                cfg_edit["crawl_entire_site"] = False
                cfg_edit["seed_urls"] = [u.strip() for u in seed_urls_text.splitlines() if u.strip()]

            cfg_edit["embedding_model"] = EMBEDDER_OPTIONS[embed_choice]
            cfg_edit["results_file"] = results_file_input

            cfg_edit["chat_model"] = chat_model
            cfg_edit["summary_model"] = summary_model
            cfg_edit["score_threshold"] = float(score_threshold)

            manager.save_config(current_project, cfg_edit)
            rebuild_pipelines_for_project(current_project)
            if auto_msg:
                st.info(auto_msg)
            st.success("Settings saved.")

else:
    st.title("Webly")
    st.info("Create or select a project from the sidebar to get started.")
