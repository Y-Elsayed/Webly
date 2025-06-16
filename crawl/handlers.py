class HTMLSaver:
    """
    Default extractor/callback that saves the raw HTML for each crawled page.
    Returns metadata with the URL, HTML content, and character length.
    """
    def __call__(self, url: str, html: str) -> dict:
        record = {
            "url": url,
            "html": html,
            "length": len(html)
        }
        return record
