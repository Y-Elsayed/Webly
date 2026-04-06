from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional


class BaseCrawler(ABC):
    """
    Interface for website crawlers used by the ingest pipeline.

    Implement this to replace the default Atlas-based crawler with any
    crawling backend — Playwright for JavaScript-heavy sites, Scrapy for
    large-scale crawls, a sitemap-only reader, or a simple URL list loader.

    The ingest pipeline calls ``crawl()`` and expects it to write pages
    to disk (via the ``on_page_crawled`` callback) so they can be
    processed downstream.

    Example — a sitemap-only crawler::

        class SitemapCrawler(BaseCrawler):
            def __init__(self, sitemap_url: str, output_dir: str):
                self.sitemap_url = sitemap_url
                self.output_dir = output_dir

            def crawl(
                self,
                on_page_crawled: Optional[Callable] = None,
                settings_override: Optional[Dict] = None,
                save_sitemap: bool = True,
            ):
                for url, html in fetch_sitemap_pages(self.sitemap_url):
                    if on_page_crawled:
                        on_page_crawled({"url": url, "html": html})

    The ``on_page_crawled`` callback signature is::

        def callback(page: dict) -> None:
            # page = {"url": str, "html": str}
    """

    @abstractmethod
    def crawl(
        self,
        on_page_crawled: Optional[Callable] = None,
        settings_override: Optional[Dict] = None,
        save_sitemap: bool = True,
    ) -> None:
        """Run the crawl.

        Args:
            on_page_crawled: Called with ``{"url": str, "html": str}``
                for every successfully fetched page.  If ``None``, the
                crawler should use its own default persistence strategy.
            settings_override: Optional dict of crawler settings that
                take precedence over the instance's defaults.
            save_sitemap: When ``True``, write a ``graph.json`` link-graph
                file alongside the results so the query pipeline can use
                it for graph-aware retrieval expansion.
        """

    def get_disallowed_report(self) -> Dict[str, List[str]]:
        """Return a mapping of ``{url: [reasons]}`` for skipped URLs.

        Override to expose diagnostic information about why URLs were not
        crawled.  Used by the ingest pipeline to write a debug report when
        no pages were saved.
        """
        return {}
