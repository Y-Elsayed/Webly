import os
import sys

from dotenv import load_dotenv

# keep your existing path setup (if needed)
sys.path.append(os.path.abspath("webcreeper"))

from chatbot.chatgpt_model import ChatGPTModel
from chatbot.webly_chat_agent import WeblyChatAgent
from crawl.crawler import Crawler
from pipeline.ingest_pipeline import IngestPipeline
from pipeline.query_pipeline import QueryPipeline
from vector_index.faiss_db import FaissDatabase


def build_pipelines(config, api_key: str | None = None):
    load_dotenv()
    API_KEY = api_key or os.getenv("OPENAI_API_KEY")

    # ---- normalize defaults ----
    emb = (config.get("embedding_model") or "").strip()
    if emb.lower() in ("", "default"):
        emb = "sentence-transformers/all-MiniLM-L6-v2"
        config["embedding_model"] = emb

    chat = (config.get("chat_model") or "").strip()
    if chat.lower() in ("", "default"):
        chat = "gpt-4o-mini"
        config["chat_model"] = chat

    # ---- embedder auto-detect ----
    uses_openai_embedder = emb.startswith("openai:")
    uses_summary = bool(config.get("summary_model"))

    if uses_openai_embedder:
        if not API_KEY:
            raise RuntimeError("Missing OPENAI_API_KEY (required for OpenAI embeddings).")
        from embedder.openai_embedder import OpenAIEmbedder

        embedder = OpenAIEmbedder(model_name=emb.split(":", 1)[1], api_key=API_KEY)
    else:
        from embedder.hf_sentence_embedder import HFSentenceEmbedder

        embedder = HFSentenceEmbedder(emb)

    db = FaissDatabase()
    chatbot = None
    if API_KEY:
        chatbot = ChatGPTModel(api_key=API_KEY, model=config.get("chat_model", "gpt-4o-mini"))

    summarizer = None
    if uses_summary:
        if not API_KEY:
            raise RuntimeError("Missing OPENAI_API_KEY (required for summarization).")
        from processors.text_summarizer import TextSummarizer

        summary_llm = ChatGPTModel(api_key=API_KEY, model=config["summary_model"])
        summarizer = TextSummarizer(
            llm=summary_llm,
            prompt_template="Summarize the following webpage clearly:\n\n{text}",
        )

    crawler = Crawler(
        start_url=config["start_url"],
        allowed_domains=config.get("allowed_domains", []),
        output_dir=config["output_dir"],
        results_filename=config.get("results_file", "results.jsonl"),
        default_settings={
            "crawl_entire_website": config.get("crawl_entire_site", True),
            "max_depth": int(config.get("max_depth", 3)),
            "allowed_paths": config.get("allowed_paths", []),
            "blocked_paths": config.get("blocked_paths", []),
            "allow_url_patterns": config.get("allow_url_patterns", []),
            "block_url_patterns": config.get("block_url_patterns", []),
            "allow_subdomains": bool(config.get("allow_subdomains", False)),
            "respect_robots": bool(config.get("respect_robots", True)),
            "rate_limit_delay": float(config.get("rate_limit_delay", 0.2)),
            "seed_urls": config.get("seed_urls", []),
        },
    )

    ingest_pipeline = IngestPipeline(
        crawler=crawler,
        index_path=config["index_dir"],
        embedder=embedder,
        db=db,
        summarizer=summarizer,
        use_summary=bool(summarizer),
        debug=True,
    )

    query_pipeline = None
    if chatbot is not None:
        agent = WeblyChatAgent(embedder, db, chatbot)
        query_pipeline = QueryPipeline(
            chat_agent=agent,
            debug=bool(config.get("query_debug", True)),
        )

    return ingest_pipeline, query_pipeline
