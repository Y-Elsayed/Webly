import os
import sys
import streamlit as st

# ------------------------------------------------------------------------------------
# Paths & imports
# ------------------------------------------------------------------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
# Use an absolute storage root so restarts & different CWDs don't break paths
STORAGE_ROOT = os.path.join(APP_DIR, "websites_storage")

# Ensure local imports work when running "streamlit run app.py"
sys.path.append(os.path.abspath(os.path.join(APP_DIR, "..")))

from main import build_pipelines
from storage.storage_manager import StorageManager

# ------------------------------------------------------------------------------------
# Page
# ------------------------------------------------------------------------------------
st.set_page_config(page_title="Webly", layout="wide")

# ------------------------------------------------------------------------------------
# Session State Initialization
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
        "project_selector": None,  # holds the current project selected in the selector
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

# Index presence check patterns
def _index_dir_ready(index_dir: str) -> bool:
    """
    Return True if the given index_dir exists and has both an .index file
    and a metadata file (e.g., metadata.meta or metadata.json).
    """
    if not index_dir or not os.path.isdir(index_dir):
        return False
    try:
        files = os.listdir(index_dir)
    except Exception:
        return False

    has_index = any(f.lower().endswith(".index") for f in files)
    has_meta = any(f.lower().startswith("metadata") for f in files)
    return has_index and has_meta

# ------------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------------
def load_project_config(manager: StorageManager, project: str) -> dict:
    """Load config from storage and finalize computed paths (absolute)."""
    cfg = manager.get_config(project)
    paths = manager.get_paths(project)
    # Force absolute paths
    root = os.path.join(STORAGE_ROOT, project) if not os.path.isabs(paths["root"]) else paths["root"]
    index_dir = os.path.join(root, "index")
    cfg["output_dir"] = root
    cfg["index_dir"] = index_dir
    cfg["results_file"] = cfg.get("results_file", "results.jsonl")
    return cfg


def ensure_chat_payload_shape(payload):
    """Normalize saved chat payloads from older formats into the new dict shape."""
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


def rebuild_pipelines_for_project(manager: StorageManager, project: str):
    """Hard guarantee that pipelines match the current selected project."""
    if not project or project == "No projects yet":
        return
    cfg = load_project_config(manager, project)
    # Ensure directories exist
    os.makedirs(cfg["output_dir"], exist_ok=True)
    os.makedirs(cfg["index_dir"], exist_ok=True)

    st.session_state.ingest_pipeline, st.session_state.query_pipeline = build_pipelines(cfg)
    st.session_state.active_project = project
    # Reset active chat for new project context
    st.session_state.active_chat = None
    st.session_state.chat_payload = {
        "title": None,
        "settings": {"score_threshold": float(cfg.get("score_threshold", 0.5))},
        "messages": [],
    }


def ensure_project_pipelines(selected_project: str, manager: StorageManager):
    """
    Backward-compatible helper: if the active project differs from the selected
    one (or pipelines are not built), rebuild pipelines to avoid stale runs.
    """
    if (
        ("active_project" not in st.session_state)
        or (st.session_state.active_project != selected_project)
        or (st.session_state.ingest_pipeline is None)
        or (st.session_state.query_pipeline is None)
    ):
        rebuild_pipelines_for_project(manager, selected_project)


# ------------------------------------------------------------------------------------
# Storage / Projects
# ------------------------------------------------------------------------------------
# Use absolute STORAGE_ROOT to avoid CWD surprises
manager = StorageManager(STORAGE_ROOT)
projects = manager.list_projects()

# ------------------------------------------------------------------------------------
# Project select on_change callback
# ------------------------------------------------------------------------------------
def _on_project_change():
    proj = st.session_state.get("project_selector")
    if projects and proj and proj != "No projects yet":
        rebuild_pipelines_for_project(manager, proj)

# ------------------------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------------------------
with st.sidebar:
    st.header("🌐 Webly Projects")

    # --- New Project ---
    if st.button("➕ New Project"):
        st.session_state.show_new_project_form = True

    if st.session_state.get("show_new_project_form", False):
        with st.expander("Create New Project", expanded=True):
            new_name = st.text_input("Project Name", key="new_project_name")
            new_url = st.text_input("Start URL", key="new_project_url")
            new_domains = st.text_area("Allowed Domains (comma-separated)", key="new_project_domains")
            embed_choice = st.selectbox("Embedding Model", list(EMBEDDER_OPTIONS.keys()), key="new_embed_choice")

            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("✅ Create", key="create_project_btn"):
                    cfg = {
                        "start_url": new_url,
                        "allowed_domains": [d.strip() for d in new_domains.split(",") if d.strip()],
                        "embedding_model": EMBEDDER_OPTIONS[embed_choice],
                        "chat_model": "gpt-4o-mini",
                        "summary_model": "",
                        "score_threshold": 0.5,
                        "crawl_entire_site": True,
                        "results_file": "results.jsonl",
                    }
                    paths = manager.get_paths(new_name)
                    # Build absolute paths
                    root = os.path.join(STORAGE_ROOT, new_name)
                    index_dir = os.path.join(root, "index")
                    os.makedirs(index_dir, exist_ok=True)

                    cfg["output_dir"] = root
                    cfg["index_dir"] = index_dir
                    manager.create_project(new_name, cfg)

                    # Immediately select and build pipelines for the new project
                    st.session_state.show_new_project_form = False
                    st.session_state.project_selector = new_name
                    rebuild_pipelines_for_project(manager, new_name)
                    st.rerun()

            with col2:
                if st.button("❌ Cancel", key="cancel_project_btn"):
                    st.session_state.show_new_project_form = False

    # --- Project Selector ---
    if projects:
        # Keep the selector on the active project if present
        default_index = 0
        if st.session_state.active_project in projects:
            default_index = projects.index(st.session_state.active_project)
        selected = st.selectbox(
            "Select Project",
            projects,
            index=default_index,
            key="project_selector",
            on_change=_on_project_change,
        )
    else:
        selected = st.selectbox("Select Project", ["No projects yet"])

    # When a valid project is selected, load its config and ensure pipelines
    if projects and selected not in (None, "No projects yet"):
        cfg = load_project_config(manager, selected)
        ensure_project_pipelines(selected, manager)

        # --- Project Settings ---
        with st.expander("⚙️ Project Settings", expanded=False):
            cfg_edit = cfg.copy()
            cfg_edit["start_url"] = st.text_input("Start URL", cfg.get("start_url", ""))

            allowed_domains_text = ", ".join(cfg.get("allowed_domains", []))
            allowed_domains_text = st.text_area("Allowed Domains (comma-separated)", allowed_domains_text)
            # store raw text; we will clean it right before saving
            cfg_edit["allowed_domains"] = allowed_domains_text

            # Embedder dropdown
            reverse_map = {v: k for k, v in EMBEDDER_OPTIONS.items()}
            current_embed_choice = reverse_map.get(cfg.get("embedding_model"), "HuggingFace (MiniLM)")
            embed_choice = st.selectbox(
                "Embedding Model",
                list(EMBEDDER_OPTIONS.keys()),
                index=list(EMBEDDER_OPTIONS.keys()).index(current_embed_choice),
            )
            cfg_edit["embedding_model"] = EMBEDDER_OPTIONS[embed_choice]

            cfg_edit["chat_model"] = st.text_input("Chat Model", cfg.get("chat_model", "gpt-4o-mini"))
            cfg_edit["summary_model"] = st.text_input("Summary Model (optional)", cfg.get("summary_model", ""))
            cfg_edit["score_threshold"] = st.slider(
                "Default Similarity Threshold", 0.0, 1.0, float(cfg.get("score_threshold", 0.5))
            )
            cfg_edit["crawl_entire_site"] = st.checkbox(
                "Crawl entire website", value=cfg.get("crawl_entire_site", True)
            )

            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if st.button("💾 Save Project Settings"):
                    # Clean & normalize allowed domains into list
                    if isinstance(cfg_edit["allowed_domains"], str):
                        cfg_edit["allowed_domains"] = [
                            d.strip() for d in cfg_edit["allowed_domains"].split(",") if d.strip()
                        ]
                    manager.save_config(selected, cfg_edit)
                    # Immediately rebuild pipelines so the change takes effect now
                    rebuild_pipelines_for_project(manager, selected)
                    st.success("Settings saved ✅")

            with col2:
                if st.button("🚀 Run Indexing"):
                    # Guard: make sure pipelines are correct for the selected project
                    rebuild_pipelines_for_project(manager, selected)
                    with st.spinner(f"Crawling and indexing {selected}..."):
                        st.session_state.ingest_pipeline.run()

                    # After run, verify index files exist where we expect
                    ok = _index_dir_ready(cfg["index_dir"])
                    if ok:
                        st.success(f"Indexing complete for {selected} ✓")
                    else:
                        st.error(
                            f"Indexing finished but index files were not found in:\n{cfg['index_dir']}\n"
                            "Check that your ingest pipeline writes to cfg['index_dir'] and filenames include an '.index' and 'metadata.*'."
                        )

            with col3:
                if st.button("🗑️ Delete Project"):
                    st.session_state.confirm_delete = selected

        # Delete confirmation UI
        if st.session_state.get("confirm_delete") == selected:
            with st.expander(f"Confirm delete '{selected}'?", expanded=True):
                dc1, dc2 = st.columns([1, 1])
                with dc1:
                    if st.button("Yes, delete"):
                        manager.delete_project(selected)
                        st.session_state.confirm_delete = None
                        # Reset session state if we deleted the active one
                        if st.session_state.active_project == selected:
                            st.session_state.active_project = None
                            st.session_state.ingest_pipeline = None
                            st.session_state.query_pipeline = None
                            st.session_state.chat_payload = {"title": None, "settings": {"score_threshold": 0.5}, "messages": []}
                            st.session_state.active_chat = None
                        st.rerun()
                with dc2:
                    if st.button("Cancel"):
                        st.session_state.confirm_delete = None
                        st.rerun()

        # --- Chats Section ---
        st.markdown("### 💬 Chats")
        chats = manager.list_chats(selected)
        active = st.session_state.get("active_chat")

        # --- New Chat ---
        if st.button("＋ New Chat", use_container_width=True):
            base = "Chat"
            idx = 1
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
            manager.save_chat(selected, new_name, st.session_state.chat_payload)
            st.rerun()

        # --- Chat List ---
        for chat_name in chats:
            is_active = (chat_name == active)

            with st.container():
                c1, c2, c3 = st.columns([6, 1, 1])
                with c1:
                    if st.button(
                        f"💬 {chat_name}" + (" ✅" if is_active else ""),
                        key=f"sel_{chat_name}",
                        use_container_width=True,
                    ):
                        st.session_state.active_chat = chat_name
                        payload = manager.load_chat(selected, chat_name)
                        st.session_state.chat_payload = ensure_chat_payload_shape(payload)
                        st.rerun()

                with c2:
                    if st.button("📝", key=f"rn_{chat_name}", help="Rename chat"):
                        # Toggle rename row for this chat
                        currently_open = st.session_state.get("rename_chat_open", None)
                        st.session_state.rename_chat_open = None if currently_open == chat_name else chat_name
                        st.rerun()

                with c3:
                    if st.button("🗑️", key=f"del_{chat_name}", help="Delete chat"):
                        manager.delete_chat(selected, chat_name)
                        if st.session_state.get("active_chat") == chat_name:
                            st.session_state.active_chat = None
                            st.session_state.chat_payload = {
                                "title": None,
                                "settings": {"score_threshold": 0.5},
                                "messages": [],
                            }
                        st.rerun()

                # Inline rename field
                if st.session_state.get("rename_chat_open") == chat_name:
                    rn_col1, rn_col2 = st.columns([3, 1])
                    with rn_col1:
                        new_title = st.text_input("New name", value=chat_name, key=f"rn_input_{chat_name}")
                    with rn_col2:
                        if st.button("Save", key=f"rn_save_{chat_name}"):
                            manager.rename_chat(selected, chat_name, new_title)
                            if st.session_state.get("active_chat") == chat_name:
                                st.session_state.active_chat = new_title
                                st.session_state.chat_payload["title"] = new_title
                            st.session_state.rename_chat_open = None
                            st.rerun()

# ------------------------------------------------------------------------------------
# Main Area: Chat
# ------------------------------------------------------------------------------------
if projects and st.session_state.get("active_project"):
    current_project = st.session_state.active_project
    st.title(f"Webly — {current_project}")

    payload = st.session_state.get("chat_payload", {"messages": []})
    payload = ensure_chat_payload_shape(payload)

    # Render existing messages
    for msg in payload["messages"]:
        st.chat_message(msg["role"]).write(msg["content"])

    if st.session_state.get("active_chat"):
        user_input = st.chat_input("Message Webly…")
        if user_input:
            payload["messages"].append({"role": "user", "content": user_input})

            # Ensure correct project's pipelines before querying
            ensure_project_pipelines(current_project, manager)
            # Check on-disk index presence instead of in-memory FAISS handle
            cfg = load_project_config(manager, current_project)
            if not _index_dir_ready(cfg["index_dir"]):
                assistant_reply = (
                    "No index found on disk for this project. "
                    "Please run indexing first (sidebar → ⚙️ Project Settings → 🚀 Run Indexing)."
                )
            else:
                # Lazy-load if the in-memory DB isn't initialized yet
                db = st.session_state.ingest_pipeline.db
                if getattr(db, "index", None) is None:
                    try:
                        db.load(cfg["index_dir"])
                    except Exception as e:
                        assistant_reply = f"Failed to load index from disk: {e}"
                    else:
                        try:
                            assistant_reply = st.session_state.query_pipeline.query(user_input)
                        except Exception as e:
                            assistant_reply = f"Query failed after loading index: {e}"
                else:
                    try:
                        assistant_reply = st.session_state.query_pipeline.query(user_input)
                    except Exception as e:
                        assistant_reply = f"Query failed: {e}"

            payload["messages"].append({"role": "assistant", "content": assistant_reply})
            st.session_state.chat_payload = payload
            manager.save_chat(current_project, st.session_state.active_chat, payload)

            # Display just-submitted messages immediately
            st.chat_message("user").write(user_input)
            st.chat_message("assistant").write(assistant_reply)
    else:
        st.info("Start a new chat from the sidebar.")
else:
    st.title("Webly")
    st.info("Create or select a project from the sidebar to get started.")
