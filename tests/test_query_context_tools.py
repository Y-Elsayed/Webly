from webly.pipeline.query_context import QueryContextTools


def test_query_context_tools_assemble_context_returns_used_sources():
    tools = QueryContextTools()

    context, used_sources = tools.assemble_context(
        [
            {"id": "a#1", "url": "https://docs.example.com/a", "text": "Alpha", "hierarchy": ["Core"]},
            {"id": "b#1", "url": "https://docs.example.com/b", "text": "Beta", "hierarchy": ["Guides"]},
        ],
        max_chars=10000,
    )

    assert "Alpha" in context
    assert "Beta" in context
    assert used_sources == [
        {"chunk_id": "a#1", "url": "https://docs.example.com/a", "section": "Core"},
        {"chunk_id": "b#1", "url": "https://docs.example.com/b", "section": "Guides"},
    ]


def test_query_context_tools_current_sources_dedupes_chunk_and_url():
    tools = QueryContextTools()

    sources = tools.current_sources(
        [
            {"chunk_id": "a#1", "url": "https://docs.example.com/a", "section": "Core"},
            {"chunk_id": "a#1", "url": "https://docs.example.com/a", "section": "Core"},
            {"chunk_id": "b#1", "url": "https://docs.example.com/b", "section": "Guides"},
        ]
    )

    assert [source.to_dict() for source in sources] == [
        {"chunk_id": "a#1", "url": "https://docs.example.com/a", "section": "Core"},
        {"chunk_id": "b#1", "url": "https://docs.example.com/b", "section": "Guides"},
    ]
