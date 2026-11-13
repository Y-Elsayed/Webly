"""Capture identity is separate from indexing, retrieval and execution settings."""

from webcreeper.creeper_core.scope import normalize_url_identity, normalized_host, scope_allowed
from webly.contracts import ArtifactError, ConfigurationError, RunPolicyMismatch, digest_json

CAPTURE_FIELDS = (
    "start_url",
    "allowed_domains",
    "allowed_paths",
    "blocked_paths",
    "allow_url_patterns",
    "block_url_patterns",
    "allow_subdomains",
    "seed_urls",
    "crawl_entire_site",
    "max_depth",
    "respect_robots",
)
NON_CAPTURE_FIELDS = {
    "output_dir",
    "index_dir",
    "rate_limit_delay",
    "results_file",
    "embedding_model",
    "chat_model",
    "summary_model",
    "answering_mode",
    "system_prompt",
    "system_prompt_custom_override",
    "allow_generated_examples",
    "retrieval_mode",
    "builder_max_rounds",
    "leave_last_k",
    "score_threshold",
    "debug",
    "query_debug",
    "embedding_cache_dir",
}


def capture_policy(config):
    try:
        policy = {field: config[field] for field in CAPTURE_FIELDS}
        policy["start_url"] = normalize_url_identity(policy["start_url"])
        policy["seed_urls"] = [normalize_url_identity(url) for url in policy["seed_urls"]]
        policy["allowed_domains"] = sorted({normalized_host(host) for host in policy["allowed_domains"]})
        for field in ("allowed_paths", "blocked_paths", "allow_url_patterns", "block_url_patterns"):
            policy[field] = sorted(set(policy[field]))
        return {"version": 1, **policy}
    except (KeyError, ValueError, TypeError, UnicodeError):
        raise ConfigurationError("Invalid capture policy") from None


def compatibility(manifest, config):
    current = capture_policy(config)
    legacy = manifest.get("format") == 1
    if legacy:
        changed = [] if manifest.get("config_digest") == digest_json(config) else ["legacy_full_config"]
    elif manifest.get("format") == 2:
        stored = manifest.get("crawl_policy")
        if not isinstance(stored, dict) or manifest.get("crawl_policy_digest") != digest_json(stored):
            raise ArtifactError("Run capture policy is corrupt")
        changed = [field for field in ("version", *CAPTURE_FIELDS) if stored.get(field) != current.get(field)]
    else:
        raise ArtifactError("Unsupported crawl run format")
    invalid = any(not scope_allowed(url, config) for url in manifest.get("sources", {}))
    if invalid:
        changed.append("source_urls")
    return {
        "compatible": not changed,
        "legacy": legacy,
        "changed_fields": changed,
        "reason": "compatible" if not changed else "fresh_crawl_required",
        "crawl_policy_digest": digest_json(current),
    }


def require_compatible(manifest, config):
    result = compatibility(manifest, config)
    if not result["compatible"]:
        raise RunPolicyMismatch(result["changed_fields"])
    return result
