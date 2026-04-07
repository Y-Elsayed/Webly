"""
Runtime validation for PipelineConfig dicts.

Call ``validate_pipeline_config(config)`` early in ``build_pipelines()``
(after default-normalisation) to surface bad inputs with clear messages
rather than cryptic errors deep in the pipeline.
"""

from __future__ import annotations

from typing import Any


def validate_pipeline_config(config: dict) -> None:
    """Validate a PipelineConfig dict.

    Collects *all* violations before raising so callers see every problem
    at once.

    Raises
    ------
    ValueError
        If any constraint is violated.  The message lists every violation.
    """
    errors: list[str] = []

    def _check(condition: bool, msg: str) -> None:
        if not condition:
            errors.append(msg)

    # ── Required fields ──────────────────────────────────────────────────────
    for field in ("start_url", "output_dir", "index_dir"):
        v = config.get(field)
        _check(
            isinstance(v, str) and bool(v.strip()),
            f"'{field}' is required and must be a non-empty string",
        )

    # ── start_url scheme ─────────────────────────────────────────────────────
    start_url = config.get("start_url") or ""
    if start_url.strip():
        _check(
            start_url.startswith("http://") or start_url.startswith("https://"),
            f"'start_url' must start with http:// or https://, got: {start_url!r}",
        )

    # ── embedding_model format ────────────────────────────────────────────────
    emb = config.get("embedding_model")
    if emb is not None and emb != "":
        if emb.lower() not in ("default",):
            if emb.startswith("openai:"):
                _check(
                    len(emb) > len("openai:"),
                    f"'embedding_model' openai prefix must be followed by a model name, got: {emb!r}",
                )
            else:
                _check(
                    " " not in emb,
                    f"'embedding_model' must be 'openai:<model-name>' or a HuggingFace path (no spaces), got: {emb!r}",
                )

    # ── answering_mode enum ───────────────────────────────────────────────────
    answering_mode = config.get("answering_mode")
    if answering_mode is not None:
        valid_modes = {"strict_grounded", "technical_grounded", "assisted_examples"}
        _check(
            answering_mode in valid_modes,
            f"'answering_mode' must be one of {' | '.join(sorted(valid_modes))}, got: {answering_mode!r}",
        )

    # ── retrieval_mode enum ───────────────────────────────────────────────────
    retrieval_mode = config.get("retrieval_mode")
    if retrieval_mode is not None:
        _check(
            retrieval_mode in ("builder", "classic"),
            f"'retrieval_mode' must be 'builder' or 'classic', got: {retrieval_mode!r}",
        )

    # ── score_threshold range [0, 1] ──────────────────────────────────────────
    score_threshold = config.get("score_threshold")
    if score_threshold is not None:
        _check(
            isinstance(score_threshold, (int, float))
            and not isinstance(score_threshold, bool)
            and 0.0 <= float(score_threshold) <= 1.0,
            f"'score_threshold' must be a float between 0.0 and 1.0, got: {score_threshold!r}",
        )

    # ── max_depth (int >= -1, not bool) ──────────────────────────────────────
    max_depth = config.get("max_depth")
    if max_depth is not None:
        _check(
            isinstance(max_depth, int)
            and not isinstance(max_depth, bool)
            and max_depth >= -1,
            f"'max_depth' must be an integer >= -1, got: {max_depth!r}",
        )

    # ── builder_max_rounds (int >= 0, not bool) ───────────────────────────────
    builder_max_rounds = config.get("builder_max_rounds")
    if builder_max_rounds is not None:
        _check(
            isinstance(builder_max_rounds, int)
            and not isinstance(builder_max_rounds, bool)
            and builder_max_rounds >= 0,
            f"'builder_max_rounds' must be a non-negative integer, got: {builder_max_rounds!r}",
        )

    # ── rate_limit_delay (number >= 0) ────────────────────────────────────────
    rate_limit_delay = config.get("rate_limit_delay")
    if rate_limit_delay is not None:
        _check(
            isinstance(rate_limit_delay, (int, float))
            and not isinstance(rate_limit_delay, bool)
            and float(rate_limit_delay) >= 0.0,
            f"'rate_limit_delay' must be a non-negative number, got: {rate_limit_delay!r}",
        )

    if errors:
        bullet_list = "\n  - ".join(errors)
        raise ValueError(f"Invalid PipelineConfig:\n  - {bullet_list}")
