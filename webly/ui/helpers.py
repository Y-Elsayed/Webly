import os
from urllib.parse import urlparse

import streamlit as st
from openai import OpenAI

from webly.chatbot.prompts.system_prompts import AnsweringMode, apply_mode_flags, get_system_prompt


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


def _mode_default_prompt_text(mode: str, allow_generated_examples: bool) -> str:
    base = get_system_prompt(mode, custom_text="", custom_override=False)
    return apply_mode_flags(mode, base, allow_generated_examples)


def _ensure_prompt_editor_state(project: str, cfg: dict):
    mode_key = f"answering_mode__{project}"
    prompt_key = f"system_prompt_text__{project}"
    override_key = f"system_prompt_custom_override__{project}"
    allow_examples_key = f"allow_generated_examples__{project}"
    last_mode_key = f"answering_mode_last__{project}"
    last_allow_key = f"allow_generated_examples_last__{project}"
    loaded_key = "prompt_editor_loaded_project"

    if (
        st.session_state.get(loaded_key) == project
        and mode_key in st.session_state
        and prompt_key in st.session_state
        and override_key in st.session_state
        and allow_examples_key in st.session_state
        and last_mode_key in st.session_state
        and last_allow_key in st.session_state
    ):
        return mode_key, prompt_key, override_key, allow_examples_key, last_mode_key, last_allow_key

    mode = str(cfg.get("answering_mode", AnsweringMode.TECHNICAL_GROUNDED.value))
    allow_examples = bool(cfg.get("allow_generated_examples", False))
    custom_override = bool(cfg.get("system_prompt_custom_override", False))
    custom_text = str(cfg.get("system_prompt", ""))

    st.session_state[mode_key] = mode
    st.session_state[allow_examples_key] = allow_examples
    st.session_state[override_key] = custom_override
    st.session_state[prompt_key] = get_system_prompt(mode, custom_text, custom_override)
    if not custom_override:
        st.session_state[prompt_key] = _mode_default_prompt_text(mode, allow_examples)
    st.session_state[last_mode_key] = mode
    st.session_state[last_allow_key] = allow_examples
    st.session_state[loaded_key] = project
    return mode_key, prompt_key, override_key, allow_examples_key, last_mode_key, last_allow_key
