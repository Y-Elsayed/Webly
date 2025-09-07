from abc import ABC, abstractmethod
from creeper_core.utils import configure_logging
import requests
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode, parse_qsl
import urllib.robotparser as robotparser
import re, time

class BaseAgent(ABC):
    """
    A polite, resilient crawling base:
      - Session pooling, optional proxies, custom headers
      - Robots.txt (toggle via respect_robots)
      - Domain allow/deny with optional subdomain support
      - Heuristics (max URL length, tracking params)
      - Regex allow/block lists
      - Per-host rate limiting
      - Retries with backoff on transient errors
      - URL normalization (strip fragments, drop tracking params, sort query)
    """

    # Safe fallback defaults (subclasses like Atlas can override with their own DEFAULT_SETTINGS)
    DEFAULT_SETTINGS = {
        "user_agent": "DefaultCrawler",
        "timeout": 10,                    # seconds (if connect/read not provided)
        "connect_timeout": None,          # seconds
        "read_timeout": None,             # seconds
        "max_retries": 2,                 # transient retries
        "backoff_factor": 0.5,            # seconds * (2**attempt)
        "status_forcelist": [429, 500, 502, 503, 504],
        "rate_limit_delay": 0.0,          # seconds between requests per host
        "respect_robots": True,           # honor robots.txt
        "allowed_domains": [],            # exact hosts (or apex if allow_subdomains=True)
        "blocked_domains": [],            # explicit deny
        "allow_subdomains": False,        # exact host by default
        "skip_url_patterns": [],          # regex strings
        "allow_url_patterns": [],         # regex strings (if provided, must match)
        "block_url_patterns": [],         # regex strings (deny if match)
        "heuristic_skip_long_urls": True,
        "max_url_length": 200,            # conservative default (Atlas uses 2000; it overrides in its own settings)
        "heuristic_skip_state_param": True,
        "normalize_query": True,          # sort query params
        "strip_tracking_params": True,    # drop common tracking params
        "tracking_param_prefixes": ["utm_"],
        "tracking_params": ["gclid", "fbclid", "msclkid", "igshid"],
        "headers": {},                    # extra headers to merge
        "proxies": None,                  # requests proxies dict
        "follow_redirects": True,         # requests allow_redirects
        "max_content_length": None,       # bytes; skip if response declares larger
    }

    def __init__(self, settings: dict = {}):
        self.settings = {**self.DEFAULT_SETTINGS, **getattr(self, "DEFAULT_SETTINGS", {}), **settings}
        self.logger = configure_logging(self.__class__.__name__)
        self.robots_cache = {}     # host -> RobotFileParser (or None if unavailable)
        self.blacklist = set()
        self.visited = set()
        self.disallowed_reasons = {}  # url -> [reasons]

        # Compile patterns
        self.skip_url_patterns = [re.compile(p) for p in self.settings.get("skip_url_patterns", [])]
        self.allow_url_patterns = [re.compile(p) for p in self.settings.get("allow_url_patterns", [])]
        self.block_url_patterns = [re.compile(p) for p in self.settings.get("block_url_patterns", [])]

        # HTTP session (connection pooling)
        self.session = requests.Session()

        # Per-host rate limiting
        self._last_fetch = {}  # host -> timestamp

    # -------------------- abstract API --------------------

    @abstractmethod
    def crawl(self):
        pass

    @abstractmethod
    def process_data(self, data):
        pass

    # -------------------- URL & domain utils --------------------

    def _strip_fragment(self, url: str) -> str:
        parts = list(urlparse(url))
        parts[5] = ""  # fragment
        return urlunparse(parts)

    def _norm_host(self, host: str) -> str:
        if not host:
            return ""
        host = host.strip().lower().split(":", 1)[0]
        return host[4:] if host.startswith("www.") else host

    def _normalize_url(self, url: str) -> str:
        """Normalize a URL: lower scheme/host, strip fragment, drop tracking, optionally sort query."""
        if not url:
            return url
        p = urlparse(url)
        scheme = p.scheme.lower()
        netloc = self._norm_host(p.netloc)
        path = p.path or "/"
        query_pairs = parse_qsl(p.query, keep_blank_values=True)

        if self.settings.get("strip_tracking_params", True):
            prefixes = tuple((self.settings.get("tracking_param_prefixes") or []))
            drop = set(self.settings.get("tracking_params") or [])
            query_pairs = [
                (k, v) for (k, v) in query_pairs
                if (not k.lower().startswith(prefixes)) and (k.lower() not in drop)
            ]

        if self.settings.get("normalize_query", True) and query_pairs:
            query_pairs.sort(key=lambda kv: kv[0].lower())

        query = urlencode(query_pairs, doseq=True)
        parts = (scheme, netloc, path, p.params, query, "")  # empty fragment
        return urlunparse(parts)

    def get_home_url(self, url: str) -> str:
        parsed_url = urlparse(url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}"

    # -------------------- robots.txt --------------------

    def fetch_robots_txt(self, url: str):
        home_url = self.get_home_url(url)
        domain_key = urlparse(home_url).netloc
        robots_url = f"{home_url}/robots.txt"

        try:
            self.logger.info(f"Fetching robots.txt from: {home_url}")
            headers = {"User-Agent": self.settings.get("user_agent", "DefaultCrawler")}
            resp = self.session.get(
                robots_url,
                headers=headers,
                timeout=self._timeouts(),
                allow_redirects=self.settings.get("follow_redirects", True),
                proxies=self.settings.get("proxies")
            )
            if resp.status_code == 200 and resp.text:
                rp = robotparser.RobotFileParser()
                rp.parse(resp.text.splitlines())
                self.logger.info("Successfully fetched robots.txt")
                return rp
            else:
                self.logger.warning(f"No robots.txt or not 200 at {robots_url} (status {resp.status_code})")
                return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error accessing robots.txt: {e}")
            return None

    def is_allowed_by_robots(self, url: str) -> bool:
        if not self.settings.get("respect_robots", True):
            return True

        domain = self.get_home_url(url)
        domain_key = urlparse(domain).netloc

        if domain_key not in self.robots_cache:
            self.robots_cache[domain_key] = self.fetch_robots_txt(url)

        rp = self.robots_cache[domain_key]
        if rp is None:
            return True  # no robots.txt = allowed
        try:
            return rp.can_fetch(self.settings.get("user_agent", "DefaultCrawler"), url)
        except Exception:
            return True

    # -------------------- domain policy --------------------

    def is_allowed_domain(self, url: str) -> bool:
        allowed = self.settings.get('allowed_domains', []) or []
        blocked = self.settings.get('blocked_domains', []) or []
        allow_sub = self.settings.get('allow_subdomains', False)

        host = urlparse(url).netloc
        norm_host = self._norm_host(host)
        allowed_norm = [self._norm_host(h) for h in allowed]
        blocked_norm = [self._norm_host(h) for h in blocked]

        # Blocked wins
        for bd in blocked_norm:
            if norm_host == bd or (allow_sub and norm_host.endswith("." + bd)):
                return False

        if not allowed_norm:
            return True

        if allow_sub:
            return any(norm_host == h or norm_host.endswith("." + h) for h in allowed_norm)
        else:
            return norm_host in allowed_norm

    # -------------------- pattern policy --------------------

    def is_allowed_by_patterns(self, url: str) -> bool:
        # Block patterns first
        for pattern in self.block_url_patterns:
            if pattern.search(url):
                self.logger.info(f"URL blocked by block pattern: {pattern.pattern}")
                return False

        # Allow patterns (if provided, must match)
        if self.allow_url_patterns:
            for pattern in self.allow_url_patterns:
                if pattern.search(url):
                    return True
            self.logger.info(f"URL blocked by allow patterns (no match): {url}")
            return False

        # No allow list => allowed
        return True

    # -------------------- heuristics --------------------

    def should_skip_url(self, url: str) -> bool:
        norm_url = self._normalize_url(url)
        parsed = urlparse(norm_url)
        path = parsed.path
        query = parse_qs(parsed.query)

        if self.settings.get("heuristic_skip_long_urls", True):
            max_len = int(self.settings.get("max_url_length", 200))
            if len(norm_url) > max_len:
                return True

        if self.settings.get("heuristic_skip_state_param", True):
            if "state" in {k.lower() for k in query.keys()}:
                return True

        for pattern in self.skip_url_patterns:
            if pattern.search(norm_url) or pattern.search(path):
                self.logger.info(f"URL skipped by pattern: {pattern.pattern}")
                return True

        return False

    # -------------------- fetch (with backoff, rate limit) --------------------

    def _timeouts(self):
        ct = self.settings.get("connect_timeout")
        rt = self.settings.get("read_timeout")
        if ct is None and rt is None:
            t = float(self.settings.get("timeout", 10))
            return (t, t)
        return (float(ct or self.settings.get("timeout", 10)), float(rt or self.settings.get("timeout", 10)))

    def _rate_limit_sleep(self, host: str):
        delay = float(self.settings.get("rate_limit_delay", 0.0))
        if delay <= 0:
            return
        now = time.time()
        last = self._last_fetch.get(host)
        if last is not None:
            elapsed = now - last
            if elapsed < delay:
                time.sleep(delay - elapsed)
        self._last_fetch[host] = time.time()

    def fetch(self, url: str):
        # Gate by policy first
        if not self.should_visit(url):
            return None

        # Normalize for request
        url = self._normalize_url(url)
        self.visited.add(url)

        headers = {"User-Agent": self.settings.get('user_agent', 'DefaultCrawler')}
        headers.update(self.settings.get("headers", {}) or {})
        proxies = self.settings.get("proxies")
        allow_redirects = self.settings.get("follow_redirects", True)
        max_retries = int(self.settings.get("max_retries", 2))
        backoff = float(self.settings.get("backoff_factor", 0.5))
        status_forcelist = set(int(s) for s in (self.settings.get("status_forcelist") or []))

        host = urlparse(url).netloc
        for attempt in range(max_retries + 1):
            try:
                self._rate_limit_sleep(host)
                self.logger.info(f"Fetching: {url} (attempt {attempt+1}/{max_retries+1})")
                resp = self.session.get(
                    url,
                    headers=headers,
                    timeout=self._timeouts(),
                    allow_redirects=allow_redirects,
                    proxies=proxies,
                )

                # Optional size guard (if server declares)
                mcl = self.settings.get("max_content_length")
                if mcl is not None:
                    try:
                        clen = int(resp.headers.get("Content-Length", "0"))
                        if clen and clen > int(mcl):
                            self._mark_disallowed(url, f"Content-Length {clen} > max {mcl}")
                            return None
                    except ValueError:
                        pass

                if resp.status_code == 200:
                    content_type = resp.headers.get('Content-Type', '') or ''
                    return resp.text, content_type

                # Retry on transient codes
                if resp.status_code in status_forcelist and attempt < max_retries:
                    sleep_s = backoff * (2 ** attempt)
                    self.logger.warning(f"Retryable status {resp.status_code} for {url}; sleeping {sleep_s:.2f}s")
                    time.sleep(sleep_s)
                    continue

                self.logger.warning(f"Failed to fetch {url}: Status code {resp.status_code}")
                return None

            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    sleep_s = backoff * (2 ** attempt)
                    self.logger.warning(f"Error fetching {url}: {e}; retrying in {sleep_s:.2f}s")
                    time.sleep(sleep_s)
                    continue
                self.logger.error(f"Error fetching {url}: {e}")
                self.blacklist.add(url)
                return None

    # -------------------- visit policy --------------------

    def is_allowed_by_robots(self, url: str) -> bool:
        # (overridden just above; keep method name/signature)
        return super().is_allowed_by_robots(url) if hasattr(super(), "is_allowed_by_robots") else True

    def should_visit(self, url: str) -> bool:
        # Already visited?
        if url in self.visited:
            self._mark_disallowed(url, "Already visited")
            return False

        if url in self.blacklist:
            self._mark_disallowed(url, "Blacklisted URL")
            return False

        # Domain policy
        if not self.is_allowed_domain(url):
            self._mark_disallowed(url, "Disallowed domain")
            return False

        # robots.txt
        if not self.is_allowed_by_robots(url):
            self._mark_disallowed(url, "Blocked by robots.txt")
            return False

        # Heuristics & patterns
        if self.should_skip_url(url):
            self._mark_disallowed(url, "Filtered by skip rules")
            return False

        if not self.is_allowed_by_patterns(url):
            self._mark_disallowed(url, "Not matched by allow patterns")
            return False

        return True

    # -------------------- diagnostics --------------------

    def _mark_disallowed(self, url: str, reason: str):
        self.logger.info(f"Disallowed {url} -> {reason}")
        if url not in self.disallowed_reasons:
            self.disallowed_reasons[url] = []
        self.disallowed_reasons[url].append(reason)

    def get_disallowed_report(self) -> dict:
        """Return a mapping of url -> reasons why it was disallowed"""
        return self.disallowed_reasons
