import streamlit as st

from ui.helpers import _index_dir_ready
from ui.project import (
    _messages_for_memory,
    build_memory_context,
    ensure_chat_payload_shape,
    ensure_project_pipelines,
    load_project_config,
)


def render_chat_tab(current_project: str, cfg: dict, manager):
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
                    payload = ensure_chat_payload_shape(st.session_state.get("chat_payload", {}))
                    payload["settings"]["memory_reset_at"] = len(payload.get("messages", []))
                    st.session_state.chat_payload = payload
                    manager.save_chat(current_project, chat_name, payload)
                else:
                    payload = manager.load_chat(current_project, chat_name)
                    payload = ensure_chat_payload_shape(payload)
                    payload["settings"]["memory_reset_at"] = len(payload.get("messages", []))
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
            st.chat_message("user").write(user_input)
            payload["messages"].append({"role": "user", "content": user_input})
            ensure_project_pipelines(current_project, manager)
            cfg_cur = load_project_config(current_project, manager)

            if st.session_state.query_pipeline is None:
                assistant_reply = "Please add your OpenAI API key in the sidebar to enable chat."
            elif not _index_dir_ready(cfg_cur["index_dir"]):
                assistant_reply = "No index found. Please run indexing first in the Run tab."
            else:
                db = st.session_state.ingest_pipeline.db
                index_ready = getattr(db, "index", None) is not None
                if not index_ready:
                    try:
                        db.load(cfg_cur["index_dir"])
                        index_ready = True
                    except Exception as e:
                        assistant_reply = f"Failed to load index: {e}"
                if index_ready:
                    try:
                        memory_ctx = build_memory_context(
                            _messages_for_memory(payload)[:-1],
                            max_chars=2000,
                            leave_last_k=int(cfg_cur.get("leave_last_k", 0) or 0),
                        )
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
