import os
import sys
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import build_pipelines
from storage.storage_manager import StorageManager

st.set_page_config(page_title="Webly", layout="wide")

# ==============================
# Constants
# ==============================
EMBEDDER_OPTIONS = {
    "HuggingFace (MiniLM)": "sentence-transformers/all-MiniLM-L6-v2",
    "OpenAI (text-embedding-3-small)": "openai:text-embedding-3-small",
    "OpenAI (text-embedding-3-large)": "openai:text-embedding-3-large",
}

# ==============================
# Utilities
# ==============================
def ensure_project_pipelines(selected_project: str, cfg: dict):
    if ("active_project" not in st.session_state) or (st.session_state.active_project != selected_project):
        st.session_state.ingest_pipeline, st.session_state.query_pipeline = build_pipelines(cfg)
        st.session_state.active_project = selected_project
        st.session_state.active_chat = None
        st.session_state.chat_payload = {"title": None, "settings": {"score_threshold": 0.5}, "messages": []}


def load_project_config(manager: StorageManager, project: str) -> dict:
    cfg = manager.get_config(project)
    paths = manager.get_paths(project)
    cfg["output_dir"] = paths["root"]
    cfg["index_dir"] = paths["index"]
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


# ==============================
# Sidebar
# ==============================
manager = StorageManager("./websites_storage")
projects = manager.list_projects()

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
                    cfg["output_dir"] = paths["root"]
                    cfg["index_dir"] = paths["index"]
                    manager.create_project(new_name, cfg)
                    st.session_state.show_new_project_form = False
                    st.session_state.active_project = new_name
                    st.rerun()
            with col2:
                if st.button("❌ Cancel", key="cancel_project_btn"):
                    st.session_state.show_new_project_form = False

    # --- Project Selector ---
    selected = st.selectbox("Select Project", projects if projects else ["No projects yet"])

    if projects and selected not in (None, "No projects yet"):
        cfg = load_project_config(manager, selected)
        ensure_project_pipelines(selected, cfg)

        # --- Project Settings ---
        with st.expander("⚙️ Project Settings", expanded=False):
            cfg_edit = cfg.copy()
            cfg_edit["start_url"] = st.text_input("Start URL", cfg.get("start_url", ""))
            cfg_edit["allowed_domains"] = st.text_area(
                "Allowed Domains (comma-separated)", ", ".join(cfg.get("allowed_domains", []))
            ).split(",")

            # Embedder dropdown
            reverse_map = {v: k for k, v in EMBEDDER_OPTIONS.items()}
            current_embed_choice = reverse_map.get(cfg.get("embedding_model"), "HuggingFace (MiniLM)")
            embed_choice = st.selectbox(
                "Embedding Model",
                list(EMBEDDER_OPTIONS.keys()),
                index=list(EMBEDDER_OPTIONS.keys()).index(current_embed_choice)
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
                    cfg_edit["allowed_domains"] = [d.strip() for d in cfg_edit["allowed_domains"] if d.strip()]
                    manager.save_config(selected, cfg_edit)
                    st.success("Settings saved ✅")

            with col2:
                if st.button("🚀 Run Indexing"):
                    with st.spinner("Crawling and indexing..."):
                        st.session_state.ingest_pipeline.run()
                        st.success("Indexing complete")

            with col3:
                if st.button("🗑️ Delete Project"):
                    st.session_state.confirm_delete = selected
                    
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
                "messages": []
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
                        st.session_state.rename_chat_open = (
                            chat_name if st.session_state.rename_chat_open != chat_name else None
                        )

                with c3:
                    if st.button("🗑", key=f"del_{chat_name}", help="Delete chat"):
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

                    
                    


# ==============================
# Main Area: Chat
# ==============================
if projects and st.session_state.get("active_project"):
    current_project = st.session_state.active_project
    st.title(f"Webly — {current_project}")

    payload = st.session_state.get("chat_payload", {"messages": []})
    payload = ensure_chat_payload_shape(payload)
    for msg in payload["messages"]:
        st.chat_message(msg["role"]).write(msg["content"])

    if st.session_state.get("active_chat"):
        user_input = st.chat_input("Message Webly…")
        if user_input:
            payload["messages"].append({"role": "user", "content": user_input})
            if (st.session_state.ingest_pipeline.db.index is None) or (st.session_state.ingest_pipeline.db.index.ntotal == 0):
                assistant_reply = "No index found. Please run indexing first."
            else:
                assistant_reply = st.session_state.query_pipeline.query(user_input)
            payload["messages"].append({"role": "assistant", "content": assistant_reply})
            st.session_state.chat_payload = payload
            manager.save_chat(current_project, st.session_state.active_chat, payload)
            st.chat_message("user").write(user_input)
            st.chat_message("assistant").write(assistant_reply)
    else:
        st.info("Start a new chat from the sidebar.")
