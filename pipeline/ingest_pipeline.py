import os
import json
from typing import Optional, List
from crawl.crawler import Crawler
from embedder.base_embedder import Embedder
from storage.vector_db import VectorDatabase
from processors.text_summarizer import TextSummarizer
from processors.page_processor import PageProcessor
from processors.text_extractor import TrafilaturaTextExtractor
from processors.text_chunker import TextChunker

class IngestPipeline:
    def __init__(
        self,
        crawler: Crawler,
        index_path: str,
        embedder: Embedder,
        db: VectorDatabase,
        summarizer: TextSummarizer,
        results_path: Optional[str] = None,
        use_summary: bool = True
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

        # Extractor + Chunker setup
        self.page_processor = PageProcessor(
            extractor=TrafilaturaTextExtractor(),
            chunker=TextChunker()
        )

    def extract(self, override_callback=None, settings_override: dict = None):
        print("[IngestPipeline] Crawling site...")
        self.crawler.crawl(
            on_page_crawled=override_callback,
            settings_override=settings_override
        )

    def transform(self) -> List[dict]:
        print("[IngestPipeline] Transforming pages (summarize =", self.use_summary, ")")
        self.db.create(dim=self.embedder.dim)
        transformed_records = []
        debug_summary_path = "summaries_full.jsonl"
        summary_debug_file = open(debug_summary_path, "w", encoding="utf-8")

        with open(self.results_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    url = record.get("url")
                    html = record.get("html")
                    if not html:
                        continue

                    chunks = self.page_processor.process(url, html)
                    for chunk in chunks:
                        content_to_embed = chunk["text"]
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

                        json.dump({
                            "url": chunk["url"],
                            "chunk_index": chunk["chunk_index"],
                            "original": chunk["text"][:500],
                            "summary": summary_text if self.use_summary else None
                        }, summary_debug_file)
                        summary_debug_file.write("\n")

                        transformed_records.append(chunk)

                except Exception as e:
                    print(f"[IngestPipeline] Skipping record due to error: {e}")

        summary_debug_file.close()
        print(f"[IngestPipeline] Wrote debug summaries to {debug_summary_path}")
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
