import pytest

from webly.config_validator import validate_pipeline_config

BASE = {
    "start_url": "https://example.com",
    "output_dir": "/tmp/out",
    "index_dir": "/tmp/idx",
}


def cfg(**overrides):
    return {**BASE, **overrides}


# ── Valid configs ─────────────────────────────────────────────────────────────

def test_valid_minimal_config_passes():
    validate_pipeline_config(BASE)


def test_valid_full_config_passes():
    validate_pipeline_config(cfg(
        embedding_model="openai:text-embedding-3-small",
        answering_mode="technical_grounded",
        retrieval_mode="builder",
        score_threshold=0.5,
        max_depth=3,
        builder_max_rounds=2,
        rate_limit_delay=0.2,
    ))


def test_score_threshold_boundary_values_pass():
    validate_pipeline_config(cfg(score_threshold=0.0))
    validate_pipeline_config(cfg(score_threshold=1.0))


def test_max_depth_minus_one_is_valid():
    validate_pipeline_config(cfg(max_depth=-1))


def test_hf_embedding_model_passes():
    validate_pipeline_config(cfg(embedding_model="sentence-transformers/all-MiniLM-L6-v2"))


def test_openai_embedding_model_passes():
    validate_pipeline_config(cfg(embedding_model="openai:text-embedding-3-large"))


def test_valid_answering_modes_pass():
    for mode in ("strict_grounded", "technical_grounded", "assisted_examples"):
        validate_pipeline_config(cfg(answering_mode=mode))


def test_builder_max_rounds_zero_is_valid():
    validate_pipeline_config(cfg(builder_max_rounds=0))


def test_rate_limit_delay_zero_is_valid():
    validate_pipeline_config(cfg(rate_limit_delay=0))


# ── Required field violations ─────────────────────────────────────────────────

def test_missing_start_url_raises():
    c = {**BASE}
    del c["start_url"]
    with pytest.raises(ValueError, match="start_url"):
        validate_pipeline_config(c)


def test_empty_start_url_raises():
    with pytest.raises(ValueError, match="start_url"):
        validate_pipeline_config(cfg(start_url=""))


def test_missing_output_dir_raises():
    c = {**BASE}
    del c["output_dir"]
    with pytest.raises(ValueError, match="output_dir"):
        validate_pipeline_config(c)


def test_missing_index_dir_raises():
    c = {**BASE}
    del c["index_dir"]
    with pytest.raises(ValueError, match="index_dir"):
        validate_pipeline_config(c)


# ── start_url scheme ──────────────────────────────────────────────────────────

def test_bad_start_url_scheme_raises():
    with pytest.raises(ValueError, match="start_url"):
        validate_pipeline_config(cfg(start_url="ftp://x.com"))


def test_start_url_no_scheme_raises():
    with pytest.raises(ValueError, match="start_url"):
        validate_pipeline_config(cfg(start_url="example.com"))


# ── embedding_model ───────────────────────────────────────────────────────────

def test_openai_prefix_without_model_name_raises():
    with pytest.raises(ValueError, match="embedding_model"):
        validate_pipeline_config(cfg(embedding_model="openai:"))


def test_embedding_model_with_spaces_raises():
    with pytest.raises(ValueError, match="embedding_model"):
        validate_pipeline_config(cfg(embedding_model="some invalid model"))


# ── answering_mode ────────────────────────────────────────────────────────────

def test_invalid_answering_mode_raises():
    with pytest.raises(ValueError, match="answering_mode"):
        validate_pipeline_config(cfg(answering_mode="hallucinate"))


# ── retrieval_mode ────────────────────────────────────────────────────────────

def test_invalid_retrieval_mode_raises():
    with pytest.raises(ValueError, match="retrieval_mode"):
        validate_pipeline_config(cfg(retrieval_mode="turbo"))


# ── score_threshold ───────────────────────────────────────────────────────────

def test_score_threshold_above_one_raises():
    with pytest.raises(ValueError, match="score_threshold"):
        validate_pipeline_config(cfg(score_threshold=1.5))


def test_score_threshold_negative_raises():
    with pytest.raises(ValueError, match="score_threshold"):
        validate_pipeline_config(cfg(score_threshold=-0.1))


def test_score_threshold_bool_raises():
    with pytest.raises(ValueError, match="score_threshold"):
        validate_pipeline_config(cfg(score_threshold=True))


# ── max_depth ─────────────────────────────────────────────────────────────────

def test_max_depth_minus_two_raises():
    with pytest.raises(ValueError, match="max_depth"):
        validate_pipeline_config(cfg(max_depth=-2))


def test_max_depth_float_raises():
    with pytest.raises(ValueError, match="max_depth"):
        validate_pipeline_config(cfg(max_depth=3.0))


def test_max_depth_bool_raises():
    with pytest.raises(ValueError, match="max_depth"):
        validate_pipeline_config(cfg(max_depth=True))


# ── builder_max_rounds ────────────────────────────────────────────────────────

def test_builder_max_rounds_negative_raises():
    with pytest.raises(ValueError, match="builder_max_rounds"):
        validate_pipeline_config(cfg(builder_max_rounds=-1))


def test_builder_max_rounds_bool_raises():
    with pytest.raises(ValueError, match="builder_max_rounds"):
        validate_pipeline_config(cfg(builder_max_rounds=True))


# ── rate_limit_delay ──────────────────────────────────────────────────────────

def test_rate_limit_delay_negative_raises():
    with pytest.raises(ValueError, match="rate_limit_delay"):
        validate_pipeline_config(cfg(rate_limit_delay=-0.5))


def test_rate_limit_delay_bool_raises():
    with pytest.raises(ValueError, match="rate_limit_delay"):
        validate_pipeline_config(cfg(rate_limit_delay=True))


# ── Multiple violations reported together ─────────────────────────────────────

def test_multiple_violations_reported_together():
    with pytest.raises(ValueError) as exc_info:
        validate_pipeline_config(cfg(
            answering_mode="bad_mode",
            score_threshold=99.0,
        ))
    msg = str(exc_info.value)
    assert "answering_mode" in msg
    assert "score_threshold" in msg
