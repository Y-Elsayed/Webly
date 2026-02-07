from webcreeper.agents.atlas.atlas import Atlas


def test_allowed_and_blocked_paths():
    atlas = Atlas(
        settings={
            "allowed_paths": ["/docs"],
            "blocked_paths": ["/docs/private"],
        }
    )
    assert atlas.is_allowed_path("https://example.com/docs/intro") is True
    assert atlas.is_allowed_path("https://example.com/docs/private/secret") is False
    assert atlas.is_allowed_path("https://example.com/blog") is False


def test_allow_url_patterns():
    atlas = Atlas(settings={"allow_url_patterns": [r"/blog/\d{4}/"]})
    assert atlas.is_allowed_path("https://example.com/blog/2024/hello") is True
    assert atlas.is_allowed_path("https://example.com/blog/hello") is False
