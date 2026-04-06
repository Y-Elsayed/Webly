class HTMLSaver:
    """
    Default extractor/callback that saves the raw HTML for each crawled page.
    Returns metadata with the URL, HTML content, and character length.
    Skips pages with missing or empty HTML content.
    """

    def __call__(self, url: str, html: str) -> dict:
        if not url or not isinstance(url, str):
            return {}
        url = url.strip()
        if not url:
            return {}

        html = html or ""
        if not html.strip():
            return {}

        return {"url": url, "html": html, "length": len(html)}
