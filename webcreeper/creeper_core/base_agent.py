# creeper_core/base_agent.py

from abc import ABC, abstractmethod
from creeper_core.utils import configure_logging
import requests
from urllib.parse import urlparse, parse_qs

class BaseAgent(ABC):

    def __init__(self, settings: dict = {}):
        self.settings = {**self.DEFAULT_SETTINGS, **settings}
        self.logger = configure_logging(self.__class__.__name__)
        self.robots_cache = {}
        self.blacklist = set()

    @abstractmethod
    def crawl(self):
        """To be implemented by concrete crawlers."""
        pass

    @abstractmethod
    def process_data(self, data):
        """To be implemented by concrete crawlers."""
        pass

    def fetch(self, url: str):
        """
        Fetches content from the given URL.
        """
        if url in self.blacklist or self.should_skip_url(url):
            self.logger.info(f"Skipping blacklisted or filtered URL: {url}")
            return None

        try:
            self.logger.info(f"Fetching: {url}")
            headers = {
                'User-Agent': self.settings.get('user_agent', 'DefaultCrawler')
            }
            response = requests.get(url, headers=headers, timeout=self.settings.get('timeout', 10))
            if response.status_code != 200:
                self.logger.warning(f"Failed to fetch {url}: Status code {response.status_code}")
                return None
            content_type = response.headers.get('Content-Type', '')
            return response.text, content_type
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {url}: {e}")
            self.blacklist.add(url)
            return None

    def get_home_url(self, url: str) -> str:
        """
        Extracts the home URL from a given URL.
        """
        parsed_url = urlparse(url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}"

    def fetch_robots_txt(self, url: str) -> str:
        """
        Fetches the robots.txt file from the domain.
        """
        home_url = self.get_home_url(url)
        robots_url = f"{home_url}/robots.txt"
        try:
            self.logger.info(f"Fetching robots.txt from: {home_url}")
            headers = {
                'User-Agent': self.settings.get('user_agent', 'DefaultCrawler')
            }
            response = requests.get(robots_url, headers=headers, timeout=self.settings.get('timeout', 10))
            if response.status_code == 200:
                self.logger.info("Successfully fetched robots.txt")
                return response.text
            else:
                self.logger.warning(f"No robots.txt found at {robots_url}")
                return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error accessing robots.txt: {e}")
            return None

    def is_allowed_link(self, url: str) -> bool:
        """
        Determines whether a URL should be crawled.
        """
        if not self.is_allowed_domain(url):
            self.logger.info(f"Domain {urlparse(url).netloc} is not allowed")
            return False

        if not self.is_allowed_by_robots(url):
            self.logger.info(f"Link {url} is disallowed by robots.txt")
            return False

        if self.should_skip_url(url):
            self.logger.info(f"Filtered out by path rules: {url}")
            return False

        return True

    def is_allowed_domain(self, url: str) -> bool:
        allowed_domains = self.settings.get('allowed_domains', [])
        parsed_url = urlparse(url)
        return parsed_url.netloc in allowed_domains or allowed_domains == []

    def is_allowed_by_robots(self, url: str) -> bool:
        domain = self.get_home_url(url)
        domain_key = urlparse(domain).netloc

        if domain_key not in self.robots_cache:
            robots_txt = self.fetch_robots_txt(url)
            self.robots_cache[domain_key] = robots_txt

        robots_txt = self.robots_cache[domain_key]
        if robots_txt:
            return self._is_url_allowed_by_robots_txt(url, robots_txt)

        return True  # Allow if no robots.txt found

    def _is_url_allowed_by_robots_txt(self, url: str, robots_txt: str) -> bool:
        parsed_url = urlparse(url)
        path = parsed_url.path
        rules = robots_txt.splitlines()
        user_agent = None
        disallowed_paths = []

        for line in rules:
            line = line.strip()
            if line.startswith("User-agent:"):
                user_agent = line.split(":")[1].strip()
            elif line.startswith("Disallow:") and user_agent == "*":
                disallowed_path = line.split(":")[1].strip()
                disallowed_paths.append(disallowed_path)

        for disallowed_path in disallowed_paths:
            if path.startswith(disallowed_path):
                return False
        return True

    def should_skip_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        query = parse_qs(parsed.query)

        SKIP_PATHS = ["/login", "/signup", "/reset", "/auth", "/u/", "/donate"]
        if any(skip in path for skip in SKIP_PATHS):
            return True

        if len(url) > 200 or "state" in query:
            return True

        return False

    def add_to_blacklist(self, urls: list[str] | str):
        if isinstance(urls, str):
            urls = [urls]
        self.blacklist.update(urls)
        self.logger.info(f"Added to blacklist: {urls}")
