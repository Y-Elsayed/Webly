from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from creeper_core.base_agent import BaseAgent
from creeper_core.storage import save_jsonl_line, save_json
import os

class Atlas(BaseAgent):
    DEFAULT_SETTINGS = {
        "base_url": None,
        "timeout": 10,
        "user_agent": "AtlasCrawler",
        "max_depth": 3,
        "allowed_domains": [],
        "allowed_paths": [],                # Only crawl if path starts with one of these
        "blocked_paths": [],               # Skip if path starts with one of these
        "storage_path": "./data",          # Where to store output data
        "crawl_entire_website": False,     # Whether to crawl full site or by depth
        "save_results": True,              # Whether to save on_page_crawled results
        "results_filename": "results.jsonl"  # One JSON per line, good for streaming
    }

    def __init__(self, settings: dict = {}):
        self.settings = {**self.DEFAULT_SETTINGS, **settings}
        self.graph = {}
        self.visited = set()
        self.max_depth = self.settings['max_depth']
        self.crawl_entire_website = self.settings['crawl_entire_website']

        # Prepare result file path
        self.results_path = os.path.join(
            self.settings['storage_path'], self.settings['results_filename']
        )
        os.makedirs(self.settings['storage_path'], exist_ok=True)

        super().__init__(self.settings)

    def crawl(self, start_url: str, on_page_crawled=None, on_all_done=None):
        """
        Start crawling from the given start URL.
        Optionally use:
        - on_page_crawled: callback to process each page
        - on_all_done: callback called after the entire crawl
        """
        self.on_page_crawled = on_page_crawled
        self.on_all_done = on_all_done

        # Clear existing results file if saving is enabled
        if self.settings["save_results"] and os.path.exists(self.results_path):
            open(self.results_path, "w").close()

        if self.crawl_entire_website:
            self.logger.info("Crawling the entire website.")
            self._crawl_entire_site(start_url)
        else:
            self.logger.info(f"Crawling with depth limit: {self.max_depth}")
            self._crawl_page(start_url)

        # Optional post-crawl callback
        if self.on_all_done:
            self.on_all_done(self.graph)

    def _crawl_page(self, url: str, depth: int = 0):
        if depth > self.max_depth or url in self.visited:
            return

        self.logger.info(f"Crawling page: {url} (Depth: {depth})")
        if not self.is_allowed_link(url) or not self.is_allowed_path(url):
            return

        content, content_type = self.fetch(url)
        if "text/html" not in content_type:
            self.logger.info(f"Skipping non-HTML content: {url} [{content_type}]")
            return

        self.visited.add(url)
        links = []

        if content:
            links = self.extract_links(content, url)
            if self.on_page_crawled:
                result = self.on_page_crawled(url, content)
                self._save_result(result)

        self.graph[url] = links

        for link in links:
            if link not in self.visited:
                self._crawl_page(link, depth + 1)

    def _crawl_entire_site(self, start_url: str):
        domain = self.get_home_url(start_url)
        to_visit = [start_url]

        while to_visit:
            url = to_visit.pop(0)
            if url in self.visited or not self.is_allowed_link(url) or not self.is_allowed_path(url):
                continue

            self.logger.info(f"Crawling page: {url}")
            content, content_type = self.fetch(url)
            if "text/html" not in content_type:
                self.logger.info(f"Skipping non-HTML content: {url} [{content_type}]")
                continue
            self.visited.add(url)
            links = []

            if content:
                links = self.extract_links(content, url)
                if self.on_page_crawled:
                    result = self.on_page_crawled(url, content)
                    self._save_result(result)

            self.graph[url] = links

            for link in links:
                if link not in self.visited and link.startswith(domain):
                    to_visit.append(link)

    def extract_links(self, page_content: str, base_url: str) -> list:
        """
        Extract links from the page content using BeautifulSoup.
        Returns absolute links within the allowed domain.
        """
        soup = BeautifulSoup(page_content, 'html.parser')
        links = set()

        for anchor in soup.find_all('a', href=True):
            full_url = urljoin(base_url, anchor['href'])
            if self.is_allowed_link(full_url) and self.is_allowed_path(full_url):
                links.add(full_url)

        return list(links)

    def is_allowed_path(self, url: str) -> bool:
        """
        Check if the URL's path passes allowed_paths and blocked_paths filters.
        """
        path = urlparse(url).path
        allowed_paths = self.settings.get("allowed_paths", [])
        blocked_paths = self.settings.get("blocked_paths", [])

        if allowed_paths and not any(path.startswith(p) for p in allowed_paths):
            return False
        if any(path.startswith(p) for p in blocked_paths):
            return False
        return True

    def _save_result(self, result: dict):
        if self.settings["save_results"] and result:
            save_jsonl_line(self.results_path, result)

    def process_data(self, data, file_path=None):
        if file_path is None:
            file_path = os.path.join(self.settings['storage_path'], 'graph.json')
        save_json(file_path, data)

    def get_graph(self):
        """
        Return the graph (dictionary of pages and their outgoing links).
        """
        return self.graph
