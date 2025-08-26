import os
import json
from typing import Optional, List
from crawl.crawler import Crawler
from embedder.base_embedder import Embedder
from vector_index.vector_db import VectorDatabase
from processors.text_summarizer import TextSummarizer
from processors.page_processor import SemanticPageProcessor
from processors.text_chunkers import DefaultChunker
from processors.text_extractors import DefaultTextExtractor

class IngestPipeline:
    def __init__(
        self,
        crawler: Crawler,
        index_path: str,
        embedder: Embedder,
        db: VectorDatabase,
        summarizer: TextSummarizer,
        results_path: Optional[str] = None,
        use_summary: bool = True,
        debug: bool = False,
        debug_summary_path: Optional[str] = None
    ):
        self.crawler = crawler
        self.index_path = index_path
        self.embedder = embedder
        self.db = db
        self.summarizer = summarizer
        self.use_summary = use_summary
        self.results_path = results_path or os.path.join(
            crawler.output_dir, crawler.results_filename
        )
        self.debug = debug

        if debug_summary_path:
            self.debug_summary_path = debug_summary_path
        else:
            debug_dir = os.path.join(crawler.output_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            self.debug_summary_path = os.path.join(debug_dir, "summaries_full.jsonl")
            self.debug_chunks_path = os.path.join(debug_dir, "raw_chunks.jsonl")

        self.page_processor = SemanticPageProcessor(
            extractor=DefaultTextExtractor(),
            chunker=DefaultChunker()
        )

    def extract(self, override_callback=None, settings_override: dict = None):
        print("[IngestPipeline] Crawling site...")
        self.crawler.crawl(
            on_page_crawled=override_callback,
            settings_override=settings_override,
            save_sitemap=True
        )

    def transform(self) -> List[dict]:
        print(f"[IngestPipeline] Transforming pages (summarize = {self.use_summary})")
        self.db.create(dim=self.embedder.dim)
        transformed_records = []

        # --- Load site graph once ---
        graph_path = os.path.join(self.crawler.output_dir, "graph.json")
        if os.path.exists(graph_path):
            with open(graph_path, "r", encoding="utf-8") as gf:
                site_graph = json.load(gf)
        else:
            print(f"[IngestPipeline] No graph.json found at {graph_path}, continuing without link metadata.")
            site_graph = {}

        summary_debug_file = open(self.debug_summary_path, "w", encoding="utf-8") if self.debug else None
        chunk_debug_file = open(self.debug_chunks_path, "w", encoding="utf-8") if self.debug else None

        with open(self.results_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    url = record.get("url")
                    html = record.get("html")

                    if not url or not html:
                        print(f"[IngestPipeline] Skipping malformed record (missing url or html): {record}")
                        continue

                    chunks = self.page_processor.process(url, html)
                    for chunk in chunks:
                        content_to_embed = chunk.get("text", "")
                        if not isinstance(content_to_embed, str) or not content_to_embed.strip():
                            continue

                        # Debug: write raw chunks
                        if self.debug and chunk_debug_file:
                            json.dump({
                                "url": chunk.get("url", url),
                                "chunk_index": chunk.get("chunk_index", -1),
                                "text": content_to_embed,
                                "length": len(content_to_embed.split())
                            }, chunk_debug_file)
                            chunk_debug_file.write("\n")

                        summary_text = None
                        if self.use_summary:
                            summary_data = self.summarizer(url, content_to_embed)
                            if not summary_data or "summary" not in summary_data:
                                print(f"[IngestPipeline] Skipping chunk from {url} - summarizer returned nothing.")
                                continue
                            summary_text = summary_data["summary"]
                            content_to_embed = summary_text
                            chunk["summary"] = summary_text

                        embedding = self.embedder.embed(content_to_embed)
                        if embedding is None:
                            print(f"[IngestPipeline] Skipping chunk from {url} - embedding failed.")
                            continue

                        chunk["embedding"] = embedding

                        # --- Enrich with graph metadata ---
                        chunk_id = f"{url}#chunk_{chunk.get('chunk_index', -1)}"

                        # Outgoing links from this page
                        outgoing_links = site_graph.get(url, [])

                        # Incoming links pointing to this page
                        incoming_links = []
                        for from_page, links in site_graph.items():
                            for link in links:
                                if link.get("target") == url:
                                    incoming_links.append({
                                        "from_page": from_page,
                                        "anchor_text": link.get("anchor_text", ""),
                                        "source_chunk": link.get("source_chunk")
                                    })

                        chunk["metadata"] = {
                            "chunk_id": chunk_id,
                            "page_url": url,
                            "outgoing_links": outgoing_links,
                            "incoming_links": incoming_links
                        }

                        if self.debug and summary_debug_file:
                            json.dump({
                                "url": chunk.get("url", "N/A"),
                                "chunk_index": chunk.get("chunk_index", -1),
                                "original": chunk.get("text", "")[:500],
                                "summary": summary_text if self.use_summary else None
                            }, summary_debug_file)
                            summary_debug_file.write("\n")

                        transformed_records.append(chunk)

                except Exception as e:
                    print(f"[IngestPipeline] Skipping record due to error: {e}")

        if summary_debug_file:
            summary_debug_file.close()
            print(f"[IngestPipeline] Wrote debug summaries to {self.debug_summary_path}")

        if chunk_debug_file:
            chunk_debug_file.close()
            print(f"[IngestPipeline] Wrote raw chunks to {self.debug_chunks_path}")

        return transformed_records


    def load(self, records: List[dict]):
        for record in records:
            self.db.add([record])
        self.db.save(self.index_path)
        print(f"[IngestPipeline] Saved index to {self.index_path}")

    def run(self, override_callback=None, settings_override: dict = None):
        self.extract(override_callback=override_callback, settings_override=settings_override)
        records = self.transform()
        self.load(records)