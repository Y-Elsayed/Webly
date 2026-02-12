# 🌐 Webly — Give Your Website a Voice

![CI](https://github.com/Y-Elsayed/webly/actions/workflows/ci.yml/badge.svg)

**Webly** is a modular, GenAI-powered web crawling and knowledge extraction framework. It transforms any website into a structured, searchable knowledge base — enabling intelligent search, chatbots, and Retrieval-Augmented Generation (RAG) pipelines.

> _"Webly makes it feel like the website itself is answering your questions._  
> _My life have changed since I started using Webly."_  
> — *Me*


---

## 🚀 What Can Webly Do?

- 🔎 **Crawl entire websites** and intelligently extract content  
- 🧠 **Summarize and embed** content using LLMs or plug-in custom processors  
- 🧷 **Store semantic data** in JSONL or vector databases (e.g. FAISS, Qdrant)  
- 🤖 **Enable chatbots** and AI-powered search over any site  
- 🕸️ **Generate a full site graph** to analyze structure and interlinking  

---

## 💡 Why Webly?

Most websites are built for humans — not machines. Webly changes that by turning static HTML into structured knowledge:

- Build **internal site search** that actually works  
- Power **AI assistants and chatbots** on your data  
- Enhance **RAG pipelines** with high-quality domain-specific chunks  
- Conduct **semantic audits** of content  
- Index and preserve **legacy web archives**

Whether you're building a smart FAQ bot or a semantic search engine over documentation, Webly gives you the tooling to make it happen — fast.

---

## ⚙️ Key Features

-  **Modular pipeline** with clear separation of crawling, extraction, summarization, embedding, and storage  
-  **Built on WebCreeper**, a custom-designed, extensible web crawling framework  
- **Pluggable architecture**: use your own chunker, summarizer, embedder, or vector DB  
-  **CLI-ready and interactive mode** — start chatting with any website in minutes  
-  **Debug output and summary logs** for easy traceability

---

## 🔧 How It Works (Overview)

1. **Crawl** the site using WebCreeper (depth-first or full-site)  
2. **Extract and chunk** the HTML with a text processor (e.g. Trafilatura)  
3. **Summarize** content using a language model (optional)  
4. **Embed** chunks into vector representations  
5. **Store** vectors in a FAISS index  
6. **Query**: Embed a user question, retrieve top matches, and respond using LLM + context

---

## 📁 Project Structure

```
webly/
│
├── crawl/              # Crawler wrapper using WebCreeper (Atlas)
├── embedder/           # Embedding models (e.g., HuggingFace)
├── processors/         # Chunker, summarizer, and text extractor
├── storage/            # Vector DBs like FAISS
├── chatbot/            # Chat interface and LLM responder
├── pipeline/           # Ingest and query pipeline orchestrators
├── config.json         # Configuration file (sample below)
├── main.py             # Entrypoint for CLI + pipeline
```

---

## 📦 Setup

1. Clone the repo  
2. Install dependencies (Python 3.11 recommended)

```bash
pip install -r requirements.txt
```

Optional (local HF embeddings + summarization):

```bash
pip install -r requirements-ml.txt
```

If you want the old all-in-one set, use `requirements-full.txt`.

3. Add your OpenAI API key in a `.env` file (see `.env.example`):

```env
OPENAI_API_KEY=your-key-here
```

4. Create a config file (`config.json`) like:

```json
{
  "start_url": "https://example.com",
  "allowed_domains": ["example.com"],
  "output_dir": "./out_example",
  "index_dir": "./out_example/index",
  "results_file": "results.jsonl",
  "embedding_model": "all-MiniLM-L6-v2",
  "chat_model": "gpt-4o-mini"
}
```

5. Run Webly:

```bash
python main.py
```

## ⚡ Quick Start (Streamlit)

Run the UI:

```bash
streamlit run app.py
```

---

## 🧠 Example Use Case

Let’s say you want to turn your university's website into a chatbot. Simply point Webly to the homepage and it will:

- Crawl and map the site  
- Summarize academic programs, admissions, and contact pages  
- Index that knowledge into a vector database  
- Let users ask questions like “What majors does the university offer?” and get accurate, real-time answers.

---

## 🛠️ Extending Webly

Want to plug in your own LLM, switch to Qdrant, or change the extractor?

Every major component is pluggable:

```python
# Swap this in:
from my_custom.chunker import MyChunker
TextChunker() → MyChunker()
```

---

## 🧪 Built With

- [WebCreeper](https://github.com/your_username/webcreeper): Custom web crawling framework  
- Hugging Face Transformers  
- FAISS  
- OpenAI GPT Models  
- Trafilatura  
- Python 3.9+

---

## 🗺️ Roadmap

See `ROADMAP.md` for contributor-friendly WebCreeper goals.

---

## 📬 Contact

Built with ☕ by [Yassin Ali](mailto:yelsayed003@gmail.com)

---

## 🔐 Security & Responsible Crawling

- Never commit API keys or secrets. Use `.env` locally and keep it out of git.
- Webly defaults to respecting `robots.txt` and uses a small request delay. You can override these,
  but you are responsible for complying with site terms, local laws, and ethical scraping practices.

