class HTMLSaver:
    """
    Default extractor/callback that saves the raw HTML for each crawled page.
    Returns metadata with the URL, HTML content, and character length.
    Skips pages with missing or empty HTML content.
    """
    def __call__(self, url: str, html: str) -> dict:
        if not url or not isinstance(url, str):
            print(f"[HTMLSaver] Skipping record due to missing or invalid URL: {url}")
            return {}

        html = html or ""
        if not html.strip():
            print(f"[HTMLSaver] Skipping empty HTML page: {url}")
            return {}

        return {
            "url": url.strip(),
            "html": html,
            "length": len(html)
        }
