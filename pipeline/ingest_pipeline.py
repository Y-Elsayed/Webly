import os
import json
from typing import List
from crawl.run_crawler import run_crawler
from processors.html_processor import MarkdownTextExtractor
from storage.vector_db import VectorDatabase
from embedder.base_embedder import Embedder
from processors.text_summarizer import TextSummarizer

class IngestPipeline:
    def __init__(
        self,
        start_url: str,
        allowed_domains: List[str],
        output_dir: str,
        index_path: str,
        embedder: Embedder,
        db: VectorDatabase,
        summarizer: TextSummarizer,
        results_filename: str = "results.jsonl"
    ):
        self.start_url = start_url
        self.allowed_domains = allowed_domains
        self.output_dir = output_dir
        self.index_path = index_path
        self.embedder = embedder
        self.db = db
        self.summarizer = summarizer
        self.results_path = os.path.join(output_dir, results_filename)

    def run(self):
        print("[IngestPipeline] Crawling site...")
        run_crawler(
            start_url=self.start_url,
            settings={
                "allowed_domains": self.allowed_domains,
                "storage_path": self.output_dir,
                "results_filename": os.path.basename(self.results_path),
                "crawl_entire_website": True
            },
            on_page_crawled=MarkdownTextExtractor()
        )

        print("[IngestPipeline] Summarizing + embedding pages...")
        self.db.create(dim=self.embedder.dim)

        with open(self.results_path, "r", encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                text = record.get("markdown")
                if not text:
                    continue

                summary_data = self.summarizer(record["url"], text)
                summary_text = summary_data["summary"]
                embedding = self.embedder.embed(summary_text)

                record["summary"] = summary_text
                record["embedding"] = embedding
                self.db.add([record])

        self.db.save(self.index_path)
        print(f"[IngestPipeline] Saved index to {self.index_path}")
