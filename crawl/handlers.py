class HTMLSaver:
    """
    Default extractor/callback that saves the raw HTML for each crawled page.
    Returns metadata with the URL, HTML content, and character length.
    """
    def __init__(self, output_path="./data/raw_pages.jsonl"):
        self.output_path = output_path

    def __call__(self, url: str, html: str) -> dict:
        record = {
            "url": url,
            "html": html,
            "length": len(html)
        }
        return record
