import pytest

from webly._webcreeper import Atlas


@pytest.mark.parametrize("url,expected", [
    ("HTTP://WWW.Example.COM:8080/docs#part", "http://www.example.com:8080/docs"),
    ("https://example.com:443/", "https://example.com:443/"),
    ("http://[::1]:8080/", "http://[::1]:8080/"),
    ("https://User:Secret@EXAMPLE.COM:8443/a", "https://User:Secret@example.com:8443/a"),
    ("https://WWW.Example.COM?b=2&utm_source=x&a=1", "https://www.example.com/?a=1&b=2"),
    ("", ""),
])
def test_fetch_normalization_preserves_authority_and_upstream_query_rules(tmp_path, url, expected):
    crawler = Atlas({"storage_path": str(tmp_path), "respect_robots": False,
                     "tracking_param_prefixes": ["utm_"]})
    assert crawler._normalize_url(url) == expected
