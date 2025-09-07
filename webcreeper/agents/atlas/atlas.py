from urllib.parse import urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup
from creeper_core.base_agent import BaseAgent
from creeper_core.storage import save_jsonl_line, save_json
import os, hashlib, re

class Atlas(BaseAgent):
    DEFAULT_SETTINGS = {
        "base_url": None,
        "timeout": 10,
        "user_agent": "AtlasCrawler",
        "max_depth": 3,
        "allowed_domains": [],
        "allowed_paths": [],
        "allow_url_patterns": [],      # regex patterns (optional allow-list)
        "blocked_paths": [],
        "storage_path": "./data",
        "crawl_entire_website": False,
        "save_results": True,
        "results_filename": "results.jsonl",
        "heuristic_skip_long_urls": True,
        "heuristic_skip_state_param": True,
        "deduplicate_content": True,
        "allow_subdomains": False,     # exact host by default
        "seed_urls": [],               # crawl only these pages when not full-site
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

        # Visited set / frontier de-dup (BaseAgent may have it; ensure present)
        if not hasattr(self, "visited"):
            self.visited = set()

        super().__init__(self.settings)

    # --------------------------- helpers ---------------------------

    def _norm_host(self, host: str) -> str:
        """lowercase, strip port and leading www."""
        if not host:
            return ""
        host = host.strip().lower()
        host = host.split(":", 1)[0]
        return host[4:] if host.startswith("www.") else host

    def _host_matches(self, host: str, allowed: str) -> bool:
        """Exact or subdomain match: foo.bar.com matches bar.com."""
        host = self._norm_host(host)
        allowed = self._norm_host(allowed)
        if not host or not allowed:
            return False
        return host == allowed or host.endswith("." + allowed)

    def _is_http(self, url: str) -> bool:
        scheme = urlparse(url).scheme.lower()
        return scheme in ("http", "https")

    def _strip_fragment(self, url: str) -> str:
        parts = list(urlparse(url))
        parts[5] = ""  # fragment
        return urlunparse(parts)

    def _should_skip_heuristics(self, url: str) -> bool:
        if self.settings.get("heuristic_skip_long_urls", True) and len(url) > 2000:
            return True
        if self.settings.get("heuristic_skip_state_param", True):
            if re.search(r"[?&](state|session|token|sid|phpsessid)=", url, re.I):
                return True
        return False

    def _effective_allowed_domains(self, start_url: str) -> list:
        """
        Build an expanded allow-list:
          - If crawl_entire_website and allowed_domains is empty, derive from start_url.
          - Always include both apex and 'www.' variant for each entry.
        """
        given = self.settings.get("allowed_domains") or []
        out = set()

        if self.crawl_entire_website and not given:
            start_host = self._norm_host(urlparse(start_url).netloc)
            if start_host:
                given = [start_host]

        for d in given:
            base = self._norm_host(d)
            if not base:
                continue
            out.add(base)
            out.add(f"www.{base}")

        return sorted(out)

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

    # ------------------------ policy checks ------------------------

    def should_visit(self, url: str) -> bool:
        """
        Normalize domain checks, optionally allow subdomains, skip bad schemes,
        and apply simple heuristics. Function name/signature preserved.
        """
        if not url:
            return False

        url = self._strip_fragment(url)

        if not self._is_http(url):
            return False

        if self._should_skip_heuristics(url):
            return False

        host = urlparse(url).netloc
        allowed_domains = self._effective_allowed_domains(self.settings.get("base_url") or url)

        # If there is an allow-list, enforce it
        if allowed_domains:
            allow_sub = self.settings.get("allow_subdomains", False)  # default exact-only
            norm_host = self._norm_host(host)
            norms = [self._norm_host(d) for d in allowed_domains]

            if allow_sub:
                ok = any(norm_host == d or norm_host.endswith("." + d) for d in norms)
            else:
                ok = norm_host in norms

            if not ok:
                self.logger.info(
                    f"Disallowed {url} -> Disallowed domain "
                    f"(host={norm_host}, allowed={norms}, allow_subdomains={allow_sub})"
                )
                return False

        return True

    def is_allowed_path(self, url: str) -> bool:
        path = urlparse(url).path or "/"
        allowed_paths = self.settings.get("allowed_paths", []) or []
        blocked_paths = self.settings.get("blocked_paths", []) or []
        allow_url_patterns = self.settings.get("allow_url_patterns", []) or []

        # Path allow-list (prefix)
        if allowed_paths and not any(path.startswith(p) for p in allowed_paths):
            return False

        # Regex allow-list (any must match)
        if allow_url_patterns:
            if not any(re.search(p, url) for p in allow_url_patterns):
                return False

        # Block-list (prefix)
        if any(path.startswith(p) for p in blocked_paths):
            return False

        return True

    # ------------------------- main crawling -----------------------

    def crawl(self, start_url: str, on_page_crawled=None, on_all_done=None):
        self.on_page_crawled = on_page_crawled
        self.on_all_done = on_all_done

        # make base_url available to domain helpers
        self.settings["base_url"] = start_url

        # reset output file if saving results
        if self.settings.get("save_results", True) and os.path.exists(self.results_path):
            open(self.results_path, "w").close()

        # reset per-run state
        self.visited = set()
        # reset dedup so new runs don't drop pages seen in previous runs
        if hasattr(self, "content_hashes"):
            self.content_hashes.clear()

        # normalize seeds list
        raw_seeds = self.settings.get("seed_urls") or []
        seeds = [u.strip() for u in raw_seeds if isinstance(u, str) and u.strip()]

        if self.crawl_entire_website:
            self.logger.info("Crawling the entire website.")
            if seeds:
                # crawl entire site using a frontier initialized by the provided seeds
                self._crawl_entire_site_from_list(seeds)
            else:
                # classic entire-site crawl starting from start_url
                self._crawl_entire_site(start_url)
        else:
            # depth-limited mode
            if seeds:
                self.logger.info(f"Crawling specific pages: {len(seeds)} URLs")
                for u in seeds:
                    self._crawl_page(u, depth=0)
            else:
                self.logger.info(f"Crawling with depth limit: {self.max_depth}")
                self._crawl_page(start_url, depth=0)

        if self.on_all_done:
            try:
                self.on_all_done(self.graph)
            except Exception as e:
                self.logger.warning(f"on_all_done callback raised: {e}")

    def _call_on_page_crawled(self, url: str, html: str):
        """
        Call user callback supporting both signatures:
          - fn(url, html)
          - fn({"url": url, "html": html})
        """
        if not self.on_page_crawled:
            return None
        try:
            return self.on_page_crawled(url, html)
        except TypeError:
            try:
                return self.on_page_crawled({"url": url, "html": html})
            except Exception as e:
                self.logger.warning(f"on_page_crawled failed for {url}: {e}")
                return None

    def _crawl_page(self, url: str, depth: int = 0):
        if (self.max_depth is not None and self.max_depth >= 0 and depth > self.max_depth) or url in self.visited:
            return

        url = self._strip_fragment(url)

        if not self.should_visit(url) or not self.is_allowed_path(url):
            return

        self.visited.add(url)
        self.logger.info(f"Crawling page: {url} (Depth: {depth})")

        fetched = self.fetch(url)
        if not fetched:
            self.logger.info(f"Skipping {url} - failed to fetch.")
            return
        content, content_type = fetched

        if not content or "text/html" not in (content_type or ""):
            self.logger.info(f"Skipping non-HTML content: {url} [{content_type}]")
            return

        # Deduplication step
        if self._is_duplicate_content(content, url):
            return

        links = self.extract_links(content, url)

        # Callback + optional save
        result = self._call_on_page_crawled(url, content)
        if isinstance(result, dict):
            self._save_result(result)

        self.graph[url] = links

        for link in links:
            self._crawl_page(link["target"], depth + 1)

    def _crawl_entire_site(self, start_url: str):
        start_url = self._strip_fragment(start_url)
        to_visit = [start_url]
        seen_frontier = set([start_url])

        while to_visit:
            url = to_visit.pop(0)
            url = self._strip_fragment(url)

            if url in self.visited:
                continue
            if not self.should_visit(url) or not self.is_allowed_path(url):
                continue

            self.visited.add(url)
            self.logger.info(f"Crawling page: {url}")

            fetched = self.fetch(url)
            if not fetched:
                self.logger.info(f"Skipping {url} - failed to fetch.")
                continue  # don't abort whole crawl

            content, content_type = fetched
            if not content or "text/html" not in (content_type or ""):
                self.logger.info(f"Skipping non-HTML content: {url} [{content_type}]")
                continue

            # Deduplication step
            if self._is_duplicate_content(content, url):
                continue

            links = self.extract_links(content, url)

            # Callback + optional save
            result = self._call_on_page_crawled(url, content)
            if isinstance(result, dict):
                self._save_result(result)

            self.graph[url] = links

            # Enqueue new links (domain policy is enforced by should_visit)
            for link in links:
                target = self._strip_fragment(link["target"])
                if target not in seen_frontier:
                    seen_frontier.add(target)
                    to_visit.append(target)

    def _crawl_entire_site_from_list(self, seed_urls):
        """
        Entire-site BFS starting from a list of seed URLs.
        Domain/path/pattern policies & robots are enforced by should_visit()/is_allowed_path().
        """
        # normalize + de-duplicate input
        frontier = []
        seen_frontier = set()

        for u in seed_urls:
            u = self._strip_fragment(u)
            if not u or u in seen_frontier:
                continue
            seen_frontier.add(u)
            frontier.append(u)

        while frontier:
            url = frontier.pop(0)
            url = self._strip_fragment(url)

            if url in self.visited:
                continue
            if not self.should_visit(url) or not self.is_allowed_path(url):
                continue

            self.visited.add(url)
            self.logger.info(f"Crawling page: {url}")

            fetched = self.fetch(url)
            if not fetched:
                self.logger.info(f"Skipping {url} - failed to fetch.")
                continue

            content, content_type = fetched
            if not content or "text/html" not in (content_type or ""):
                self.logger.info(f"Skipping non-HTML content: {url} [{content_type}]")
                continue

            # Deduplicate by page text hash (per run)
            if hasattr(self, "_is_duplicate_content") and self._is_duplicate_content(content, url):
                continue

            links = self.extract_links(content, url)

            # user callback & save
            result = self._call_on_page_crawled(url, content) if hasattr(self, "_call_on_page_crawled") else None
            if isinstance(result, dict):
                self._save_result(result)

            self.graph[url] = links

            # enqueue discovered links for full-site traversal
            for link in links:
                target = self._strip_fragment(link["target"])
                if target not in seen_frontier:
                    seen_frontier.add(target)
                    frontier.append(target)


    def extract_links(self, page_content: str, base_url: str, page_id=None) -> list:
        soup = BeautifulSoup(page_content, "html.parser")
        links = []
        seen = set()

        i = 0
        for anchor in soup.find_all("a", href=True):
            full_url = urljoin(base_url, anchor["href"])
            full_url = self._strip_fragment(full_url)
            if not self._is_http(full_url):
                continue
            if full_url in seen:
                continue
            seen.add(full_url)

            links.append({
                "target": full_url,
                "anchor_text": anchor.get_text(strip=True),
                "source_chunk": f"{page_id}_chunk_{i}" if page_id is not None else f"chunk_{i}"
            })
            i += 1

        return links

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
