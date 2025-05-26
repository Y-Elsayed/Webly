from webcreeper.agents.atlas.atlas import Atlas


def save_html_callback(url, html):
    return {"url": url, "html": html}


def run_crawler(
    start_url: str,
    allowed_domains: list,
    output_dir: str = "./out",
    on_page_crawled=None,
    results_filename="results.jsonl"
):
    """
    Runs Atlas to crawl a website and process each page.

    Args:
        start_url (str): The starting URL for the crawl.
        allowed_domains (list): Domains that are allowed to be crawled.
        output_dir (str): Where to save the results.
        on_page_crawled (callable): Function to call for each page. Should return a dict.
        results_filename (str): Output file name for processed results.
    """
    settings = { # check the settings structure in the Atlas class
        "base_url": start_url,
        "allowed_domains": allowed_domains,
        "crawl_entire_website": True,
        "storage_path": output_dir,
        "results_filename": results_filename,
        "save_results": True
    }
    
    callback = on_page_crawled if on_page_crawled is not None else save_html_callback # uses the default callback, which saves the whole HTML

    atlas = Atlas(settings=settings)
    atlas.crawl(start_url, on_page_crawled=callback)
    atlas.process_data(atlas.get_graph())  # Saving the website structure (pages and links)
