import os
import sys
import json
from dotenv import load_dotenv

# ─── Setup and Imports ──────────────────────────────────────────────────────────
sys.path.append(os.path.abspath("webcreeper"))  # Temporary patch until proper install

from embedder.hf_sentence_embedder import HFSentenceEmbedder
from chatbot.chatgpt_model import ChatGPTModel
from chatbot.webly_chat_agent import WeblyChatAgent
from pipeline.query_pipeline import QueryPipeline
from pipeline.ingest_pipeline import IngestPipeline
from processors.text_summarizer import TextSummarizer
from storage.faiss_db import FaissDatabase
from crawl.crawler import Crawler

# ─── Load Configuration ─────────────────────────────────────────────────────────
with open("config.json", "r") as f:
    config = json.load(f)

START_URL = config["start_url"]
ALLOWED_DOMAINS = config["allowed_domains"]
OUTPUT_DIR = config["output_dir"]
INDEX_DIR = config["index_dir"]
RESULTS_PATH = os.path.join(OUTPUT_DIR, config["results_file"])
EMBEDDING_MODEL = config["embedding_model"]
SCORE_THRESHOLD = config.get("score_threshold", 0.6)
CHAT_MODEL = config.get("chat_model", "gpt-4o-mini")
SUMMARY_MODEL = config.get("summary_model", "gpt-4o-mini")

# ─── Load Environment Variables ────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY in .env or environment variables.")

# ─── Initialize Core Components ────────────────────────────────────────────────
embedder = HFSentenceEmbedder(EMBEDDING_MODEL)
db = FaissDatabase()
chatbot = ChatGPTModel(api_key=API_KEY, model=CHAT_MODEL)
summary_llm = ChatGPTModel(api_key=API_KEY, model=SUMMARY_MODEL)

# ─── Set Up Summarizer ─────────────────────────────────────────────────────────
SUMMARY_PROMPT = (
    "You are a documentation assistant. Summarize the following webpage content clearly and concisely.\n"
    "Focus on the main purpose and key information relevant to a reader skimming the content:\n\n{text}"
)
summarizer = TextSummarizer(llm=summary_llm, prompt_template=SUMMARY_PROMPT)

# ─── Set Up Crawler ────────────────────────────────────────────────────────────
crawler = Crawler(
    start_url=START_URL,
    allowed_domains=ALLOWED_DOMAINS,
    output_dir=OUTPUT_DIR,
    results_filename=config["results_file"],
    default_settings={
        "crawl_entire_website": True
    }
)

# ─── Ingest Pipeline: Crawl → Summarize → Embed → Store ────────────────────────
ingest_pipeline = IngestPipeline(
    crawler=crawler,
    index_path=INDEX_DIR,
    embedder=embedder,
    db=db,
    summarizer=summarizer,
    use_summary=False,
    debug=True
)

try:
    if not os.path.exists(os.path.join(INDEX_DIR, "embeddings.index")):
        print("[Webly] Crawling and indexing site...")
        ingest_pipeline.run()
        print("[Webly] Indexing complete.")
    else:
        db.load(INDEX_DIR)
except Exception as e:
    print(f"[Webly] Failed to initialize index: {e}")
    sys.exit(1)

# ─── Query Pipeline: Embed → Retrieve → Answer ─────────────────────────────────
agent = WeblyChatAgent(embedder, db, chatbot)
query_pipeline = QueryPipeline(chat_agent=agent)

# ─── CLI Loop ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n[Webly] Ready.\nAsk a question (press enter to quit):\n")
    while True:
        question = input("You: ").strip()
        if not question:
            print("Goodbye!")
            break
        answer = query_pipeline.query(question)
        print(f"\nWebly: {answer}\n")
