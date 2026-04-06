import streamlit as st

from webly.chatbot.prompts.system_prompts import AnsweringMode
from webly.ui.helpers import (
    _domain_from_url,
    _ensure_prompt_editor_state,
    _mode_default_prompt_text,
)
from webly.ui.project import rebuild_pipelines_for_project
from webly.ui.state import EMBEDDER_OPTIONS


def render_settings_tab(current_project: str, cfg: dict, manager):
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
        mode_key, prompt_key, override_key, allow_examples_key, last_mode_key, last_allow_key = (
            _ensure_prompt_editor_state(current_project, cfg)
        )
        reset_pending_key = f"system_prompt_reset_pending__{current_project}"

        def _mark_custom_override():
            current_text = (st.session_state.get(prompt_key) or "").strip()
            if current_text:
                st.session_state[override_key] = True
                return
            st.session_state[override_key] = False
            st.session_state[reset_pending_key] = True

        if st.session_state.pop(reset_pending_key, False):
            st.session_state[prompt_key] = _mode_default_prompt_text(
                st.session_state[mode_key], st.session_state[allow_examples_key]
            )
            st.session_state[override_key] = False

        mode_labels = [
            AnsweringMode.STRICT_GROUNDED.value,
            AnsweringMode.TECHNICAL_GROUNDED.value,
            AnsweringMode.ASSISTED_EXAMPLES.value,
        ]
        if st.session_state[mode_key] not in mode_labels:
            st.session_state[mode_key] = AnsweringMode.TECHNICAL_GROUNDED.value

        answering_mode = st.selectbox(
            "Answering mode",
            mode_labels,
            key=mode_key,
            help=(
                "strict_grounded: policy/compliance/marketing sites; high trust; avoid inference.\n"
                "technical_grounded: developer/API docs; allow reasoning strictly derived from context.\n"
                "assisted_examples: onboarding/tutorial style; optional generated examples with explicit labeling."
            ),
        )

        allow_generated_examples = st.checkbox(
            "Allow generated examples (assisted_examples only)",
            key=allow_examples_key,
            help=(
                "When enabled in assisted_examples mode, generated examples are allowed only with explicit label:\n"
                "'GENERATED EXAMPLE (not from documentation)'."
            ),
        )

        mode_changed = st.session_state[mode_key] != st.session_state.get(last_mode_key)
        allow_changed = st.session_state[allow_examples_key] != st.session_state.get(last_allow_key)
        if (mode_changed or allow_changed) and not st.session_state[override_key]:
            st.session_state[prompt_key] = _mode_default_prompt_text(
                st.session_state[mode_key], st.session_state[allow_examples_key]
            )
        st.session_state[last_mode_key] = st.session_state[mode_key]
        st.session_state[last_allow_key] = st.session_state[allow_examples_key]

        system_prompt_input = st.text_area(
            "System prompt (actual prompt used for this project)",
            key=prompt_key,
            height=220,
            on_change=_mark_custom_override,
            help=(
                "This field always shows the actual prompt that will be sent to the LLM.\n"
                "If you edit it manually, it becomes a custom override and mode changes won't overwrite it."
            ),
        )

        c_reset, c_state = st.columns([1, 2])
        with c_reset:
            if st.button("Reset to mode default"):
                st.session_state[reset_pending_key] = True
                st.rerun()
        with c_state:
            if st.session_state[override_key]:
                st.caption("Prompt source: custom override")
            else:
                st.caption("Prompt source: mode default")

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
        retrieval_mode = st.selectbox(
            "Retrieval mode",
            ["classic", "builder"],
            index=0 if str(cfg.get("retrieval_mode", "builder")) == "classic" else 1,
            help="classic: existing flow. builder: concept-aware context building with limited follow-up searches.",
        )
        builder_max_rounds = st.number_input(
            "Builder max rounds",
            min_value=0,
            max_value=3,
            value=int(cfg.get("builder_max_rounds", 1)),
            help="How many follow-up retrieval rounds builder mode can run.",
            disabled=(retrieval_mode == "classic"),
        )
        leave_last_k = st.number_input(
            "Leave last K Q/A pairs in memory (0 = default)",
            min_value=0,
            max_value=20,
            value=int(cfg.get("leave_last_k", 2)),
            help="When >0, memory context includes only the last K user+assistant pairs.",
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
        cfg_edit["answering_mode"] = answering_mode
        cfg_edit["allow_generated_examples"] = bool(allow_generated_examples)
        cfg_edit["system_prompt_custom_override"] = bool(st.session_state.get(override_key, False))
        cfg_edit["system_prompt"] = system_prompt_input
        cfg_edit["summary_model"] = summary_model
        cfg_edit["score_threshold"] = float(score_threshold)
        cfg_edit["retrieval_mode"] = retrieval_mode
        cfg_edit["builder_max_rounds"] = int(builder_max_rounds)
        cfg_edit["leave_last_k"] = int(leave_last_k)

        manager.save_config(current_project, cfg_edit)
        rebuild_pipelines_for_project(current_project, manager)
        if auto_msg:
            st.info(auto_msg)
        st.success("Settings saved.")
