from webcreeper.agents.atlas.atlas import Atlas


def save_html_callback(url, html):
    return {"url": url, "html": html}


def run_crawler(
    start_url: str,
    settings: dict = None,
    on_page_crawled=None
):
    """
    Crawl a website using Atlas.

    Args:
        start_url (str): The URL to start from.
        settings (dict): Dictionary of crawler settings (overrides Atlas.DEFAULT_SETTINGS).
        on_page_crawled (callable, optional): Callback function to process each page.
    """
    default_settings = {
        "base_url": start_url,
        "allowed_domains": [],
        "storage_path": "./out",
        "results_filename": "results.jsonl",
        "crawl_entire_website": True,
        "timeout": 10,
        "user_agent": "AtlasCrawler",
        "max_depth": 3,
        "allowed_paths": [],
        "blocked_paths": [],
        "save_results": True,
    }

    final_settings = {**default_settings, **(settings or {})}
    final_settings["base_url"] = start_url  # always override with current

    callback = on_page_crawled if on_page_crawled is not None else save_html_callback

    atlas = Atlas(settings=final_settings)
    atlas.crawl(start_url, on_page_crawled=callback)
    atlas.process_data(atlas.get_graph())

