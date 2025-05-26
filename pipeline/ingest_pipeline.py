import os
import json
from typing import Optional, List
from crawl.crawler import Crawler
from embedder.base_embedder import Embedder
from storage.vector_db import VectorDatabase
from processors.text_summarizer import TextSummarizer

class IngestPipeline:
    def __init__(
        self,
        crawler: Crawler,
        index_path: str,
        embedder: Embedder,
        db: VectorDatabase,
        summarizer: TextSummarizer,
        results_path: Optional[str] = None
    ):
        """
        Args:
            crawler (Crawler): A configured Crawler instance.
            index_path (str): Where to save the vector index and metadata.
            embedder (Embedder): Embedder to convert text into vectors.
            db (VectorDatabase): A vector database (e.g., FAISS).
            summarizer (TextSummarizer): Summarizer instance.
            results_path (str, optional): Path to the JSONL file of crawled data.
                                          If not provided, inferred from crawler.
        """
        self.crawler = crawler
        self.index_path = index_path
        self.embedder = embedder
        self.db = db
        self.summarizer = summarizer
        self.results_path = results_path or os.path.join(
            crawler.output_dir, crawler.results_filename
        )

    def extract(self, override_callback=None, settings_override: dict = None):
        """
        Runs the crawler. Optionally override the page callback or settings.
        """
        print("[IngestPipeline] Crawling site...")
        self.crawler.crawl(
            on_page_crawled=override_callback,
            settings_override=settings_override
        )

    def transform(self) -> List[dict]:
        """
        Reads the results JSONL, summarizes and embeds each entry.
        Returns the transformed records.
        """
        print("[IngestPipeline] Summarizing + embedding pages...")
        self.db.create(dim=self.embedder.dim)
        transformed_records = []

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
                transformed_records.append(record)

        return transformed_records

    def load(self, records: List[dict]):
        """
        Stores the transformed records in the vector database and saves it.
        """
        for record in records:
            self.db.add([record])
        self.db.save(self.index_path)
        print(f"[IngestPipeline] Saved index to {self.index_path}")

    def run(self, override_callback=None, settings_override: dict = None):
        """
        Runs the full extract-transform-load pipeline.
        """
        self.extract(override_callback=override_callback, settings_override=settings_override)
        records = self.transform()
        self.load(records)
