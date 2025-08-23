from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from creeper_core.base_agent import BaseAgent
from creeper_core.storage import save_jsonl_line, save_json
import os, hashlib

class Atlas(BaseAgent):
    DEFAULT_SETTINGS = {
        "base_url": None,
        "timeout": 10,
        "user_agent": "AtlasCrawler",
        "max_depth": 3,
        "allowed_domains": [],
        "allowed_paths": [],
        "allow_url_patterns": [],
        "blocked_paths": [],
        "storage_path": "./data",
        "crawl_entire_website": False,
        "save_results": True,
        "results_filename": "results.jsonl",
        "heuristic_skip_long_urls": True,
        "heuristic_skip_state_param": True,
        "deduplicate_content": True,   # NEW: enable dedup by default
    }

    def __init__(self, settings: dict = {}):
        self.settings = {**self.DEFAULT_SETTINGS, **settings}
        self.graph = {}
        self.max_depth = self.settings["max_depth"]
        self.crawl_entire_website = self.settings["crawl_entire_website"]

        self.results_path = os.path.join(
            self.settings["storage_path"], self.settings["results_filename"]
        )
        os.makedirs(self.settings["storage_path"], exist_ok=True)

        # Track seen content hashes
        self.content_hashes = set()

        super().__init__(self.settings)

    # --- helpers ---
    def _is_duplicate_content(self, html: str, url: str) -> bool:
        """Check if content is duplicate based on hash of extracted text."""
        if not self.settings.get("deduplicate_content", True):
            return False

        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        if not text:
            return False

        h = hashlib.md5(text.encode("utf-8")).hexdigest()
        if h in self.content_hashes:
            self.logger.info(f"Skipping {url} (duplicate content hash)")
            return True

        self.content_hashes.add(h)
        return False

    # --- main crawling ---
    def crawl(self, start_url: str, on_page_crawled=None, on_all_done=None):
        self.on_page_crawled = on_page_crawled
        self.on_all_done = on_all_done

        if self.settings["save_results"] and os.path.exists(self.results_path):
            open(self.results_path, "w").close()

        if self.crawl_entire_website:
            self.logger.info("Crawling the entire website.")
            self._crawl_entire_site(start_url)
        else:
            self.logger.info(f"Crawling with depth limit: {self.max_depth}")
            self._crawl_page(start_url)

        if self.on_all_done:
            self.on_all_done(self.graph)

    def _crawl_page(self, url: str, depth: int = 0):
        if depth > self.max_depth or url in self.visited:
            return

        self.logger.info(f"Crawling page: {url} (Depth: {depth})")
        if not self.should_visit(url) or not self.is_allowed_path(url):
            return

        fetched = self.fetch(url)
        if not fetched:
            self.logger.info(f"Skipping {url} - failed to fetch.")
            return
        content, content_type = fetched

        if not content or "text/html" not in content_type:
            self.logger.info(f"Skipping non-HTML content: {url} [{content_type}]")
            return

        # Deduplication step
        if self._is_duplicate_content(content, url):
            return

        links = self.extract_links(content, url)
        if self.on_page_crawled:
            result = self.on_page_crawled(url, content)
            if not isinstance(result, dict):
                self.logger.warning(f"on_page_crawled for {url} returned invalid result: {result}")
                result = {}
            self._save_result(result)

        self.graph[url] = links

        for link in links:
            self._crawl_page(link["target"], depth + 1)

    def _crawl_entire_site(self, start_url: str):
        domain = self.get_home_url(start_url)
        to_visit = [start_url]

        while to_visit:
            url = to_visit.pop(0)
            if not self.should_visit(url) or not self.is_allowed_path(url):
                continue

            self.logger.info(f"Crawling page: {url}")
            fetched = self.fetch(url)
            if not fetched:
                self.logger.info(f"Skipping {url} - failed to fetch.")
                return
            content, content_type = fetched

            if not content or "text/html" not in content_type:
                self.logger.info(f"Skipping non-HTML content: {url} [{content_type}]")
                continue

            # Deduplication step
            if self._is_duplicate_content(content, url):
                continue

            links = self.extract_links(content, url)
            if self.on_page_crawled:
                result = self.on_page_crawled(url, content)
                if not isinstance(result, dict):
                    self.logger.warning(f"on_page_crawled for {url} returned invalid result: {result}")
                    result = {}
                self._save_result(result)

            self.graph[url] = links

            for link in links:
                target = link["target"]
                if target.startswith(domain) and target not in to_visit:
                    to_visit.append(target)

    def extract_links(self, page_content: str, base_url: str, page_id=None) -> list:
        soup = BeautifulSoup(page_content, "html.parser")
        links = []
        for i, anchor in enumerate(soup.find_all("a", href=True)):
            full_url = urljoin(base_url, anchor["href"])
            links.append({
                "target": full_url,
                "anchor_text": anchor.get_text(strip=True),
                "source_chunk": f"{page_id}_chunk_{i}"
            })
        return links

    def is_allowed_path(self, url: str) -> bool:
        path = urlparse(url).path
        allowed_paths = self.settings.get("allowed_paths", [])
        blocked_paths = self.settings.get("blocked_paths", [])

        if allowed_paths and not any(path.startswith(p) for p in allowed_paths):
            return False
        if any(path.startswith(p) for p in blocked_paths):
            return False
        return True

    def _save_result(self, result: dict):
        if not isinstance(result, dict):
            return
        if "url" not in result or "html" not in result or not result["html"]:
            self.logger.debug(f"Skipping result due to missing fields: {result}")
            return
        if self.settings["save_results"]:
            save_jsonl_line(self.results_path, result)

    def process_data(self, data, file_path=None):
        if file_path is None:
            file_path = os.path.join(self.settings["storage_path"], "graph.json")
        save_json(file_path, data)

    def get_graph(self):
        return self.graph
