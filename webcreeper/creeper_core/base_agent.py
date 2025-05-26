# creeper_core/base_agent.py
from abc import ABC, abstractmethod
from creeper_core.utils import configure_logging
import requests
from urllib.parse import urlparse

class BaseAgent(ABC):

    def __init__(self, settings: dict = {}):
        self.settings = {**self.DEFAULT_SETTINGS, **settings}  # Merging default and passed settings
        self.logger = configure_logging(self.__class__.__name__)
        self.robots_cache = {} # Cache for robots.txt content
        self.blacklist = set()  # List of URLs to ignore

    @abstractmethod
    def crawl(self):
        """
        Abstract method to be implemented by all crawlers.
        Defines the main crawling logic.
        """
        pass

    @abstractmethod
    def process_data(self, data):
        """
        Abstract method to process raw data.
        """
        pass

    def fetch(self, url: str):
        """
        Fetches content from the given URL using settings from self.settings.
        """
        if url in self.blacklist:
            self.logger.info(f"Skipping blacklisted URL: {url}")
            return None
        try:
            self.logger.info(f"Fetching: {url}")
            headers = {
                'User-Agent': self.settings.get('user_agent', 'DefaultCrawler')  # Using the user agent from settings and defaulting to 'DefaultCrawler'
            }
            response = requests.get(url, headers=headers, timeout=self.settings.get('timeout', 10))  # Using timeout from settings and defaulting to 10 seconds
            if response.status_code != 200:
                self.logger.warning(f"Failed to fetch {url}: Status code {response.status_code}")
                return None
            content_type = response.headers.get('Content-Type', '')
            return response.text, content_type # Returning the HTML content of the page and the content type in case is is needed
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {url}: {e}")
            self.blacklist.add(url)  # Add to blacklist on error
            return None


    def get_home_url(self, url: str) -> str:
        """
        Extracts the home URL from a given URL.
        """
        self.logger.info(f"Extracting home URL from: {url}")
        parsed_url = urlparse(url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    #Should be used in each crawler to check if the URL is allowed to be crawled
    def fetch_robots_txt(self, url: str) -> str:
        """
        Fetches the robots.txt file from the home of the website.
        """
        home_url = self.get_home_url(url)
        robots_url = f"{home_url}/robots.txt"
        try:
            self.logger.info(f"Fetching robots.txt from: {home_url}")
            headers = {
                'User-Agent': self.settings.get('user_agent', 'DefaultCrawler')
            }
            response = requests.get(robots_url, headers=headers, timeout=self.settings.get('timeout', 10)) # Using timeout from settings and defaulting to 10 seconds
            if response.status_code == 200:
                self.logger.info("Successfully fetched robots.txt")
                return response.text
            else:
                self.logger.warning(f"No robots.txt found at {robots_url}") # Logging a warning if no robots.txt is found
                return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error accessing robots.txt: {e}") # Logging an error if there is an exception
            return None

    def is_allowed_link(self, url: str) -> bool:
        """
        Check if the link is within the allowed domains and allowed by robots.txt.
        """
        if not self.is_allowed_domain(url):
            self.logger.info(f"Domain {urlparse(url).netloc} is not allowed")
            return False

        # Check if the URL is allowed by robots.txt
        if not self.is_allowed_by_robots(url):
            self.logger.info(f"Link {url} is disallowed by robots.txt")
            return False

        return True

    def is_allowed_domain(self, url: str) -> bool:
        """
        Check if the domain is within the allowed domains.
        """
        allowed_domains = self.settings.get('allowed_domains', [])
        parsed_url = urlparse(url)
        if parsed_url.netloc not in allowed_domains and allowed_domains != []:
            return False
        return True
    

    def is_allowed_by_robots(self, url: str) -> bool:
        """
        Checks if the URL is allowed by the robots.txt file for the domain.
        """
        domain = self.get_home_url(url)  # Get the base URL (domain)
        domain_key = urlparse(domain).netloc  # Extract domain from URL

        # Check if we already have the robots.txt content cached for this domain
        if domain_key not in self.robots_cache:
            robots_txt = self.fetch_robots_txt(url)
            self.robots_cache[domain_key] = robots_txt

        # If we have robots.txt cached for this domain
        if domain_key in self.robots_cache:
            robots_txt = self.robots_cache[domain_key]
            return self._is_url_allowed_by_robots_txt(url, robots_txt)

        # If no robots.txt found, allow crawling by default
        return True

    def _is_url_allowed_by_robots_txt(self, url: str, robots_txt: str) -> bool:
        """
        Parses the robots.txt content and checks if the URL is allowed.
        """
        parsed_url = urlparse(url)
        path = parsed_url.path

        # Split robots.txt into lines and filter out comments
        rules = robots_txt.splitlines()
        user_agent = None
        disallowed_paths = []

        for line in rules:
            line = line.strip()
            if line.startswith("User-agent:"):
                user_agent = line.split(":")[1].strip()
            elif line.startswith("Disallow:") and user_agent == "*" :
                disallowed_path = line.split(":")[1].strip()
                disallowed_paths.append(disallowed_path)

        # Check if the URL path matches any disallowed path
        for disallowed_path in disallowed_paths:
            if path.startswith(disallowed_path):
                return False
        return True
    
    def add_to_blacklist(self, urls: list[str] | str):
        if isinstance(urls, str):
            urls = [urls]
        self.blacklist.update(urls)
        self.logger.info(f"Added to blacklist: {urls}")
