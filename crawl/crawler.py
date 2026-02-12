from webcreeper.agents.atlas.atlas import Atlas

from .handlers import HTMLSaver


class Crawler:
    def __init__(
        self,
        start_url: str,
        allowed_domains: list,
        output_dir: str,
        results_filename: str = "results.jsonl",
        default_callback=None,
        default_settings=None,
    ):
        self.start_url = start_url
        self.allowed_domains = allowed_domains
        self.output_dir = output_dir
        self.results_filename = results_filename
        self.default_callback = default_callback or HTMLSaver()

        self.default_settings = {
            "base_url": start_url,
            "allowed_domains": allowed_domains,
            "storage_path": output_dir,
            "results_filename": results_filename,
            "crawl_entire_website": True,
        }

        if default_settings:
            self.default_settings.update(default_settings)

    def crawl(self, on_page_crawled=None, settings_override=None, save_sitemap=True):
        settings = self.default_settings.copy()
        if settings_override:
            settings.update(settings_override)

        atlas = Atlas(settings=settings)
        callback = on_page_crawled or self.default_callback
        atlas.crawl(self.start_url, on_page_crawled=callback)
        if save_sitemap:
            atlas.process_data(atlas.get_graph())
