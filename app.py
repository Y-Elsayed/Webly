import os
import sys
import streamlit as st

# Allow imports from parent directory (where main.py is)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import build_pipelines         # refactored entrypoint you added
from storage.storage_manager import StorageManager

st.set_page_config(page_title="Webly", layout="wide")

# ==============================
# Utilities
# ==============================
def ensure_project_pipelines(selected_project: str, cfg: dict):
    if ("active_project" not in st.session_state) or (st.session_state.active_project != selected_project):
        st.session_state.ingest_pipeline, st.session_state.query_pipeline = build_pipelines(cfg)
        st.session_state.active_project = selected_project
        st.session_state.active_chat = None
        st.session_state.chat_payload = {"title": None, "settings": {"score_threshold": 0.5}, "messages": []}

        db = st.session_state.ingest_pipeline.db
        if db.index is not None:
            st.caption(f"Index loaded • vectors: {db.index.ntotal}")
        else:
            st.caption("Index not loaded")

        index_dir = cfg["index_dir"]
        emb = os.path.join(index_dir, "embeddings.index")
        meta = os.path.join(index_dir, "metadata.meta")
        if db.index is None and os.path.exists(emb) and os.path.exists(meta):
            db.load(index_dir)



def load_project_config(manager: StorageManager, project: str) -> dict:
    cfg = manager.get_config(project)
    paths = manager.get_paths(project)
    cfg["output_dir"] = paths["root"]
    cfg["index_dir"] = paths["index"]
    cfg["results_file"] = cfg.get("results_file", "results.jsonl")
    return cfg


def ensure_chat_payload_shape(payload):
    """Backward-compatible: convert old list format to new dict payload."""
    # New shape:
    # {
    #   "title": "Chat 1",
    #   "settings": {"score_threshold": 0.5},
    #   "messages": [{"role":"user","content":...},{"role":"assistant","content":...}]
    # }
    if isinstance(payload, list):
        msgs = []
        for item in payload:
            # old tuple/list like [question, answer]
            if isinstance(item, (list, tuple)) and len(item) == 2:
                msgs.append({"role": "user", "content": item[0]})
                msgs.append({"role": "assistant", "content": item[1]})
        return {"title": "Imported Chat", "settings": {"score_threshold": 0.5}, "messages": msgs}

    # If already dict, ensure keys exist
    payload.setdefault("title", "Untitled Chat")
    payload.setdefault("settings", {"score_threshold": 0.5})
    payload.setdefault("messages", [])
    payload["settings"].setdefault("score_threshold", 0.5)
    return payload


# ==============================
# App State
# ==============================
if "show_new_project_form" not in st.session_state:
    st.session_state.show_new_project_form = False

if "rename_chat_open" not in st.session_state:
    st.session_state.rename_chat_open = None  # holds chat name being renamed

# ==============================
# Sidebar: Project & Chats (ChatGPT-like)
# ==============================
manager = StorageManager("./websites_storage")
projects = manager.list_projects()

with st.sidebar:
    st.markdown(
        """
        <style>
            .side-header { font-size: 1.1rem; font-weight: 600; margin-top: 0.5rem; }
            .chat-item { padding: .4rem .6rem; border-radius: 8px; margin-bottom: .2rem; cursor: pointer; }
            .chat-item:hover { background: rgba(127,127,127,0.15); }
            .chat-item.active { background: rgba(127,127,127,0.25); }
            .chat-row { display:flex; align-items:center; justify-content:space-between; gap:.4rem; }
            .chat-title { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
            .chat-actions button { padding:0 .3rem !important; }
            .new-chat-btn { width: 100%; }
            .project-select { margin-top:.25rem; }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Header
    st.markdown('<div class="side-header">🌐 Webly Project Manager</div>', unsafe_allow_html=True)

    # New Project modal-like expander toggle
    col_np1, col_np2 = st.columns([1, 1])
    with col_np1:
        if st.button("➕ New Project"):
            st.session_state.show_new_project_form = True
    with col_np2:
        # simple spacing for aesthetics
        st.write("")

    # New Project "modal" in sidebar
    if st.session_state.show_new_project_form:
        with st.expander("🆕 Create New Project", expanded=True):
            new_name = st.text_input("Project Name", key="new_project_name")
            new_url = st.text_input("Start URL", key="new_project_url")
            new_domains = st.text_area("Allowed Domains (comma-separated)", key="new_project_domains")
            c1, c2, c3 = st.columns([1,1,1])
            with c1:
                if st.button("Create"):
                    # inside the " Create" handler in your New Project expander
                    cfg = {
                        "start_url": new_url,
                        "allowed_domains": [d.strip() for d in new_domains.split(",") if d.strip()],
                        # USE REAL DEFAULTS:
                        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",  # 384-dim, fast & popular
                        "chat_model": "gpt-4o-mini",
                        "summary_model": "",
                        "score_threshold": 0.5,
                        "crawl_entire_site": True,
                        "results_file": "results.jsonl",
                    }

                    paths = manager.get_paths(new_name)
                    cfg["output_dir"] = paths["root"]
                    cfg["index_dir"] = paths["index"]
                    manager.create_project(new_name, cfg)
                    # auto-select it
                    st.session_state.show_new_project_form = False
                    st.session_state.active_project = new_name
                    st.rerun()
            with c2:
                if st.button("❌ Cancel"):
                    st.session_state.show_new_project_form = False
            with c3:
                if st.button("✖ Close"):
                    st.session_state.show_new_project_form = False

    # Project selector
    selected = st.selectbox("Project", projects if projects else ["No projects yet"], key="project_select", help="Choose which website/project to chat with.")

    if projects and selected not in (None, "No projects yet"):
        cfg = load_project_config(manager, selected)
        ensure_project_pipelines(selected, cfg)

        # New Chat button
        if st.button("＋ New chat", key="new_chat_sidebar_btn", help="Start a new conversation for this project.", use_container_width=True):
            # auto name Chat 1, Chat 2...
            base = "Chat"
            existing = manager.list_chats(selected)
            idx = 1
            new_name = f"{base} {idx}"
            while new_name in existing:
                idx += 1
                new_name = f"{base} {idx}"
            # initialize
            st.session_state.active_chat = new_name
            st.session_state.chat_payload = {"title": new_name, "settings": {"score_threshold": cfg.get("score_threshold", 0.5)}, "messages": []}
            manager.save_chat(selected, new_name, st.session_state.chat_payload)
            st.rerun()

        # Chat list
        st.markdown('<div class="side-header">Chats</div>', unsafe_allow_html=True)
        chats = manager.list_chats(selected)
        active = st.session_state.get("active_chat")

        # Draw each chat item row with select + inline actions
        for chat_name in chats:
            is_active = (chat_name == active)
            with st.container():
                # Row
                c1, c2, c3 = st.columns([8, 1, 1])
                with c1:
                    # selecting a chat loads it
                    if st.button(f"💬 {chat_name}", key=f"sel_{chat_name}", help="Open chat", use_container_width=True):
                        st.session_state.active_chat = chat_name
                        payload = manager.load_chat(selected, chat_name)
                        st.session_state.chat_payload = ensure_chat_payload_shape(payload)
                        st.rerun()

                with c2:
                    # rename toggle
                    if st.button("📝", key=f"rn_{chat_name}", help="Rename chat"):
                        st.session_state.rename_chat_open = chat_name if st.session_state.rename_chat_open != chat_name else None
                with c3:
                    # delete
                    if st.button("🗑", key=f"del_{chat_name}", help="Delete chat"):
                        manager.delete_chat(selected, chat_name)
                        if st.session_state.get("active_chat") == chat_name:
                            st.session_state.active_chat = None
                            st.session_state.chat_payload = {"title": None, "settings": {"score_threshold": 0.5}, "messages": []}
                        st.rerun()

                # Inline rename input if toggled
                if st.session_state.rename_chat_open == chat_name:
                    rn_col1, rn_col2 = st.columns([3,1])
                    with rn_col1:
                        new_title = st.text_input("New name", value=chat_name, key=f"rn_input_{chat_name}")
                    with rn_col2:
                        if st.button("Save", key=f"rn_save_{chat_name}"):
                            manager.rename_chat(selected, chat_name, new_title)
                            # Update active chat if needed
                            if st.session_state.get("active_chat") == chat_name:
                                st.session_state.active_chat = new_title
                                st.session_state.chat_payload["title"] = new_title
                            st.session_state.rename_chat_open = None
                            st.rerun()

        # Project settings (view/edit)
        with st.expander("⚙️ Project Settings", expanded=False):
            cfg_edit = cfg.copy()
            cfg_edit["start_url"] = st.text_input("Start URL", cfg.get("start_url", ""))
            cfg_edit["allowed_domains"] = st.text_area("Allowed Domains (comma-separated)", ", ".join(cfg.get("allowed_domains", []))).split(",")
            cfg_edit["embedding_model"] = st.text_input("Embedding Model", cfg.get("embedding_model", "default"))
            cfg_edit["chat_model"] = st.text_input("Chat Model", cfg.get("chat_model", "default"))
            cfg_edit["summary_model"] = st.text_input("Summary Model (optional)", cfg.get("summary_model", ""))
            cfg_edit["score_threshold"] = st.slider("Default Similarity Threshold (fallback)", 0.0, 1.0, float(cfg.get("score_threshold", 0.5)))
            cfg_edit["crawl_entire_site"] = st.checkbox("Crawl entire website", value=cfg.get("crawl_entire_site", True))

            csave, cidx = st.columns([1,1])
            with csave:
                if st.button("💾 Save Project Settings"):
                    # normalize domains
                    cfg_edit["allowed_domains"] = [d.strip() for d in cfg_edit["allowed_domains"] if d.strip()]
                    manager.save_config(selected, cfg_edit)
                    st.success("Saved")
            with cidx:
                if st.button("🚀 Run Indexing Now"):
                    with st.spinner("Crawling and indexing..."):
                        st.session_state.ingest_pipeline.run()
                        st.success("Indexing complete")

# ==============================
# Main: Chat Area
# ==============================
if projects and st.session_state.get("active_project"):
    current_project = st.session_state.active_project
    st.title(f"Webly — {current_project}")

    # Chat Settings (per chat)
    left, right = st.columns([4, 1])
    with right:
        if st.session_state.get("active_chat"):
            with st.expander("Chat Settings", expanded=False):
                payload = st.session_state.chat_payload
                payload = ensure_chat_payload_shape(payload)
                thr = st.slider("Similarity threshold", 0.0, 1.0, float(payload["settings"].get("score_threshold", 0.5)))
                if thr != payload["settings"].get("score_threshold", 0.5):
                    payload["settings"]["score_threshold"] = thr
                    st.session_state.chat_payload = payload
                    # Persist immediately
                    manager.save_chat(current_project, st.session_state.active_chat, st.session_state.chat_payload)
                st.caption("Stored with this chat. (If your retrieval pipeline supports it, results below this score can be filtered.)")

    # Render history (ChatGPT style)
    payload = st.session_state.get("chat_payload", {"messages": []})
    payload = ensure_chat_payload_shape(payload)
    for msg in payload["messages"]:
        st.chat_message(msg["role"]).write(msg["content"])

    # Input (Enter to send)
    if st.session_state.get("active_chat"):
        user_input = st.chat_input("Message Webly…")
        if user_input:
            # Append user message
            payload["messages"].append({"role": "user", "content": user_input})

            # Ensure index exists before querying
            if (st.session_state.ingest_pipeline.db.index is None) or (st.session_state.ingest_pipeline.db.index.ntotal == 0):
                assistant_reply = "No index found for this project. Please run indexing first."
            else:
                # Optional: you can pass the threshold into your pipeline if supported.
                # For example, if QueryPipeline accepts a threshold, set it before calling query:
                # st.session_state.query_pipeline.score_threshold = payload["settings"]["score_threshold"]
                assistant_reply = st.session_state.query_pipeline.query(user_input)

            payload["messages"].append({"role": "assistant", "content": assistant_reply})
            st.session_state.chat_payload = payload
            manager.save_chat(current_project, st.session_state.active_chat, st.session_state.chat_payload)

            # Stream the last two messages
            st.chat_message("user").write(user_input)
            st.chat_message("assistant").write(assistant_reply)
    else:
        st.info("Start a new chat from the sidebar.")
else:
    st.title("Webly")
    st.info("Create or select a project from the left sidebar to begin.")
