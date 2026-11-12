"""Environment resolution for reference applications, outside the Core factory."""

from pathlib import Path

from webly.contracts import ConfigurationError, ResourceScope
from webly.project_config import ProjectConfig
from webly.providers import ModelCapabilities, ProviderBundle


def application_providers(config, api_key=None):
    raw = config.to_dict() if isinstance(config, ProjectConfig) else dict(config)
    embedding = raw.get("embedding_model") or "openai:text-embedding-3-small"
    if embedding.startswith("openai:"):
        from webly.embedder.openai_embedder import OpenAIEmbedder

        if not api_key:
            raise ConfigurationError("An explicit API key is required for OpenAI embeddings")
        model = embedding.split(":", 1)[1]
        if model not in {"text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"}:
            raise ConfigurationError("Supply explicit ProviderBundle capabilities for an unknown embedding model")
        embedder = OpenAIEmbedder(model_name=model, api_key=api_key)
    else:
        from webly.embedder.hf_sentence_embedder import HFSentenceEmbedder

        embedder = HFSentenceEmbedder(embedding)
    chat = None
    generation = None
    summary = None
    summary_spec = None
    if api_key:
        from webly.chatbot.chatgpt_model import ChatGPTModel

        model = raw.get("chat_model") or "gpt-4o-mini"
        known = {
            "gpt-4o-mini": 128000,
            "gpt-4o": 128000,
            "gpt-4.1": 1_000_000,
            "gpt-4.1-mini": 1_000_000,
            "gpt-4.1-nano": 1_000_000,
        }
        if model not in known or (raw.get("summary_model") and raw["summary_model"] not in known):
            raise ConfigurationError("Supply explicit ProviderBundle capabilities for unknown chat models")
        chat = ChatGPTModel(api_key=api_key, model=model)
        generation = ModelCapabilities(model, known[model])
        if raw.get("summary_model"):
            model = raw["summary_model"]
            summary = ChatGPTModel(api_key=api_key, model=model)
            summary_spec = ModelCapabilities(model, known[model])
    return ProviderBundle(
        embedder,
        ModelCapabilities(embedding, embedder.max_input_tokens, dimensions=embedder.dim),
        chat,
        generation,
        summary,
        summary_spec,
    )


def build_application_runtime(config, api_key=None):
    import os

    from dotenv import load_dotenv

    from webly.runtime import build_runtime

    load_dotenv()
    raw = config.to_dict() if isinstance(config, ProjectConfig) else dict(config)
    root = Path(raw.get("output_dir") or ".") / "core-v2"
    resource_id = "project"
    providers = application_providers(raw, api_key=api_key or os.getenv("OPENAI_API_KEY"))
    clean = {
        key: value
        for key, value in raw.items()
        if key not in {"output_dir", "index_dir", "embedding_cache_dir", "results_file"}
    }
    try:
        runtime = build_runtime(clean, resources=ResourceScope(resource_id, root), providers=providers)
    except Exception:
        providers.close()
        raise
    runtime._owns_providers = True
    return runtime
