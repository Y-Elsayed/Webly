import logging
import os

import streamlit as st

logger = logging.getLogger(__name__)

from webly import build_pipelines
from webly.ui.state import STORAGE_ROOT


def load_project_config(project: str, manager) -> dict:
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
    payload["settings"].setdefault("memory_reset_at", 0)
    return payload


def build_memory_context(messages, max_chars: int = 2000, leave_last_k: int = 0) -> str:
    """Build a compact memory string from the most recent chat messages."""
    if not messages:
        return ""
    if leave_last_k and leave_last_k > 0:
        messages = messages[-(leave_last_k * 2):]
    buf = []
    total = 0
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


def _messages_for_memory(payload: dict) -> list:
    msgs = list(payload.get("messages", []))
    settings = payload.get("settings", {}) or {}
    try:
        reset_at = int(settings.get("memory_reset_at", 0) or 0)
    except Exception as e:
        logger.debug(f"memory_reset_at is not a valid int ({settings.get('memory_reset_at')!r}), defaulting to 0: {e}")
        reset_at = 0
    if reset_at <= 0:
        return msgs
    return msgs[reset_at:]


def rebuild_pipelines_for_project(project: str, manager, api_key: str | None = None):
    if not project or project == "No projects yet":
        return
    cfg = load_project_config(project, manager)
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


def ensure_project_pipelines(selected_project: str, manager):
    has_key = bool(st.session_state.get("user_openai_key"))
    if (
        ("active_project" not in st.session_state)
        or (st.session_state.active_project != selected_project)
        or (st.session_state.ingest_pipeline is None)
        or (has_key and st.session_state.query_pipeline is None)
    ):
        rebuild_pipelines_for_project(
            selected_project,
            manager,
            api_key=st.session_state.get("user_openai_key"),
        )
