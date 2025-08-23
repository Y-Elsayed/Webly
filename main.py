# main.py
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath("webcreeper"))

from embedder.hf_sentence_embedder import HFSentenceEmbedder
from embedder.openai_embedder import OpenAIEmbedder  # <-- new embedder
from chatbot.chatgpt_model import ChatGPTModel
from chatbot.webly_chat_agent import WeblyChatAgent
from pipeline.query_pipeline import QueryPipeline
from pipeline.ingest_pipeline import IngestPipeline
from processors.text_summarizer import TextSummarizer
from vector_index.faiss_db import FaissDatabase
from crawl.crawler import Crawler


def build_pipelines(config):
    load_dotenv()
    API_KEY = os.getenv("OPENAI_API_KEY")
    if not API_KEY:
        raise RuntimeError("Missing OPENAI_API_KEY")

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
    if emb.startswith("openai:"):
        embedder = OpenAIEmbedder(model_name=emb.split(":", 1)[1], api_key=API_KEY)
    else:
        embedder = HFSentenceEmbedder(emb)

    db = FaissDatabase()
    chatbot = ChatGPTModel(api_key=API_KEY, model=config.get("chat_model", "gpt-4o-mini"))

    summarizer = None
    if config.get("summary_model"):
        summary_llm = ChatGPTModel(api_key=API_KEY, model=config["summary_model"])
        summarizer = TextSummarizer(
            llm=summary_llm,
            prompt_template="Summarize the following webpage clearly:\n\n{text}",
        )

    crawler = Crawler(
        start_url=config["start_url"],
        allowed_domains=config["allowed_domains"],
        output_dir=config["output_dir"],
        results_filename=config["results_file"],
        default_settings={"crawl_entire_website": config.get("crawl_entire_site", True)},
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

    agent = WeblyChatAgent(embedder, db, chatbot)
    query_pipeline = QueryPipeline(chat_agent=agent)

    return ingest_pipeline, query_pipeline
