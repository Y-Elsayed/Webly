import os
import sys
import json
import streamlit as st

# Allow imports from parent directory (where main.py is)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import ingest_pipeline, query_pipeline  # Make sure main.py exposes these

CONFIG_PATH = "config.json"

# === Utility Functions ===
def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {
            "start_url": "",
            "allowed_domains": [],
            "embedding_model": "default",
            "chat_model": "default",
            "score_threshold": 0.5,
            "crawl_entire_site": True,
            "url_patterns": [],
            "exclude_patterns": []
        }
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

# === Sidebar Configuration ===
st.sidebar.title("Webly Configuration")

cfg = load_config()

start_url = st.sidebar.text_input("Start URL", cfg.get("start_url", ""))
allowed_domains = st.sidebar.text_area("Allowed Domains (comma-separated)", ", ".join(cfg.get("allowed_domains", [])))
embedding_model = st.sidebar.text_input("Embedding Model", cfg.get("embedding_model", "default"))
chat_model = st.sidebar.text_input("Chat Model", cfg.get("chat_model", "default"))
score_threshold = st.sidebar.slider("Score Threshold", 0.0, 1.0, float(cfg.get("score_threshold", 0.5)))

crawl_entire_site = st.sidebar.checkbox("Crawl entire website", value=cfg.get("crawl_entire_site", True))

with st.sidebar.expander("Advanced URL Filters"):
    url_patterns = st.text_area("Include URL patterns (wildcards allowed)", "\n".join(cfg.get("url_patterns", [])))
    exclude_patterns = st.text_area("Exclude patterns (e.g., *.pdf, /admin/*)", "\n".join(cfg.get("exclude_patterns", [])))

if st.sidebar.button("Save Settings"):
    cfg.update({
        "start_url": start_url,
        "allowed_domains": [d.strip() for d in allowed_domains.split(",") if d.strip()],
        "embedding_model": embedding_model,
        "chat_model": chat_model,
        "score_threshold": score_threshold,
        "crawl_entire_site": crawl_entire_site,
        "url_patterns": [p.strip() for p in url_patterns.splitlines() if p.strip()],
        "exclude_patterns": [p.strip() for p in exclude_patterns.splitlines() if p.strip()]
    })
    save_config(cfg)
    st.sidebar.success("Settings saved")

# === Main Interface ===
st.title("Webly")

st.markdown("""
<style>
.user-bubble {
    background-color: #808080;
    padding: 10px 15px;
    border-radius: 12px;
    margin: 10px 0;
    max-width: 80%;
    align-self: flex-end;
}
.webly-bubble {
    background-color: #808080;
    padding: 10px 15px;
    border-radius: 12px;
    margin: 10px 0;
    max-width: 80%;
    align-self: flex-start;
}
.chat-container {
    display: flex;
    flex-direction: column;
}
</style>
""", unsafe_allow_html=True)

if st.button("Run Indexing"):
    with st.spinner("Running the ingestion pipeline..."):
        ingest_pipeline.run()
        st.success("Indexing complete")

st.divider()

# === Chat Interface with History ===
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

query = st.text_input("Ask a question")

if query:
    response = query_pipeline.query(query)
    st.session_state.chat_history.append((query, response))

st.markdown('<div class="chat-container">', unsafe_allow_html=True)
for q, r in st.session_state.chat_history:
    st.markdown(f'<div class="user-bubble"><strong>You:</strong> {q}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="webly-bubble"><strong>Webly:</strong> {r}</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
