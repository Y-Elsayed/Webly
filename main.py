import os
import json
from dotenv import load_dotenv
import sys

sys.path.append(os.path.abspath("webcreeper"))  # temp fix to include the webcreeper package until I get it to properly install

from embedder.hf_sentence_embedder import HFSentenceEmbedder
from chatbot.chatgpt_model import ChatGPTModel
from chatbot.webly_chat_agent import WeblyChatAgent
from pipeline.query_pipeline import QueryPipeline
from pipeline.ingest_pipeline import IngestPipeline
from processors.text_summarizer import TextSummarizer
from storage.faiss_db import FaissDatabase
from crawl.crawler import Crawler


# --- Load configuration ---
with open("config.json", "r") as f:
    config = json.load(f)

START_URL = config["start_url"]
ALLOWED_DOMAINS = config["allowed_domains"]
OUTPUT_DIR = config["output_dir"]
INDEX_DIR = config["index_dir"]
RESULTS_PATH = os.path.join(OUTPUT_DIR, config["results_file"])
EMBEDDING_MODEL = config["embedding_model"]
SCORE_THRESHOLD = config.get("score_threshold", 0.6)
EMBEDDING_FIELD = config.get("embedding_field", "markdown")
CHAT_MODEL = config.get("chat_model", "gpt-4o-mini")
SUMMARY_MODEL = config.get("summary_model", "gpt-4o-mini")  # fallback to gpt-4o-mini


# I am testing using GPT's API, so I need to load but anyone can comment it out if they are using anything else
# --- load api key ---
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY in .env or environment variables.")


# ----- init main components -----
embedder = HFSentenceEmbedder(EMBEDDING_MODEL)
db = FaissDatabase()
chatbot = ChatGPTModel(api_key=API_KEY, model=CHAT_MODEL)
summary_llm = ChatGPTModel(api_key=API_KEY, model=SUMMARY_MODEL)

# Summary prompt template for doc-style summarization
SUMMARY_PROMPT = (
    "You are a documentation assistant. Summarize the following webpage content clearly and concisely.\n"
    "Focus on the main purpose and key information relevant to a reader skimming the content:\n\n{text}"
)

summarizer = TextSummarizer(llm=summary_llm, prompt_template=SUMMARY_PROMPT)

crawler = Crawler(
    start_url=START_URL,
    allowed_domains=ALLOWED_DOMAINS,
    output_dir=OUTPUT_DIR,
    results_filename=config["results_file"],
    default_settings={  # moved here!
        "crawl_entire_website": True
    }
)

# --- Ingest pipeline: crawl -> summarize -> embed -> store ---
ingest_pipeline = IngestPipeline(
    crawler=crawler,
    index_path=INDEX_DIR,
    embedder=embedder,
    db=db,
    summarizer=summarizer
)

if not os.path.exists(os.path.join(INDEX_DIR, "embeddings.index")):
    ingest_pipeline.run()
else:
    db.load(INDEX_DIR)


# --- Query pipeline: embed query -> retrieve -> answer ---
agent = WeblyChatAgent(embedder, db, chatbot)
query_pipeline = QueryPipeline(chat_agent=agent, score_threshold=SCORE_THRESHOLD)


# --- Run interactive CLI ---
if __name__ == "__main__":
    print("\n[Webly] Ready. Ask a question (press enter to quit):\n")
    while True:
        question = input("You: ").strip()
        if not question:
            print("Goodbye!")
            break
        answer = query_pipeline.query(question)
        print(f"\nWebly: {answer}\n")
