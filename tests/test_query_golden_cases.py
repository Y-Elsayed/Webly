from tests.query_eval_harness import ScriptedPlanner, run_query_case


def test_golden_classic_initial_answerable_query_result():
    result = run_query_case(
        results_by_query={
            "What is Webly?": [
                {
                    "id": "overview-1",
                    "url": "https://docs.example.com/overview",
                    "text": "Webly is a modular website-to-RAG framework for crawl, ingest, and chat retrieval.",
                    "hierarchy": ["Overview"],
                    "score": 0.96,
                }
            ]
        },
        question="What is Webly?",
        retrieval_mode="classic",
        enable_hybrid=False,
        enable_rewrite=False,
        enable_graph_expansion=False,
        enable_section_expansion=False,
        answer_fn=lambda _question, _context: "Webly is a modular website-to-RAG framework.",
        judge_fn=lambda _question, context: "website-to-rag framework" in context.lower(),
    )

    assert result.supported is True
    assert result.answer == "Webly is a modular website-to-RAG framework."
    assert [source.url for source in result.sources] == ["https://docs.example.com/overview"]
    assert result.trace["mode"] == "classic"
    assert result.trace["answer_path"] == "answerable_initial"


def test_golden_classic_rewrite_rescues_missing_initial_context():
    result = run_query_case(
        results_by_query={
            "How do retries work?": [
                {
                    "id": "intro-1",
                    "url": "https://docs.example.com/intro",
                    "text": "This page introduces reliability concepts at a high level.",
                    "hierarchy": ["Guides"],
                    "score": 0.65,
                }
            ],
            "retry policy details": [
                {
                    "id": "retry-1",
                    "url": "https://docs.example.com/retries",
                    "text": "Retry policy uses exponential backoff with jitter and a five-attempt cap.",
                    "hierarchy": ["Reliability"],
                    "score": 0.94,
                }
            ],
        },
        question="How do retries work?",
        retrieval_mode="classic",
        enable_hybrid=False,
        enable_graph_expansion=False,
        enable_section_expansion=False,
        rewrite_fn=lambda _question, _hints: "retry policy details",
        answer_fn=lambda _question, _context: "Retries use exponential backoff with jitter and stop after five attempts.",
        judge_fn=lambda _question, context: "exponential backoff with jitter" in context.lower(),
    )

    assert result.supported is True
    assert result.trace["answer_path"] == "answerable_hop_1"
    assert result.trace["combined_result_count"] >= 2
    assert [source.url for source in result.sources] == [
        "https://docs.example.com/retries",
        "https://docs.example.com/intro",
    ]


def test_golden_builder_transform_only_uses_memory_not_retrieval():
    result = run_query_case(
        results_by_query={},
        question="Rewrite that as bullets.",
        memory_context="Webly crawls websites and turns them into retrieval-ready knowledge.",
        retrieval_mode="builder",
        planner=ScriptedPlanner(
            route_payload={"mode": "transform_only", "standalone_query": "", "concepts": []},
            transform_response="- Crawls websites\n- Builds retrieval-ready knowledge",
        ),
        enable_hybrid=False,
    )

    assert result.supported is True
    assert result.sources == []
    assert result.answer == "- Crawls websites\n- Builds retrieval-ready knowledge"
    assert result.trace["route_mode"] == "transform_only"
    assert result.trace["answer_path"] == "transform_only"


def test_golden_builder_best_effort_keeps_used_source_links():
    result = run_query_case(
        results_by_query={
            "How does retry backoff work?": [
                {
                    "id": "retry-1",
                    "url": "https://docs.example.com/retries",
                    "text": "Retries use exponential backoff.",
                    "hierarchy": ["Reliability"],
                    "score": 0.93,
                }
            ]
        },
        question="How does retry backoff work?",
        retrieval_mode="builder",
        planner=ScriptedPlanner(
            route_payload={
                "mode": "retrieve_new",
                "standalone_query": "",
                "concepts": ["retry", "jitter"],
            }
        ),
        enable_hybrid=False,
        enable_graph_expansion=False,
        enable_section_expansion=False,
        answer_with_support_fn=lambda _question, _context: (
            "Retries use exponential backoff. Jitter is not covered in the retrieved docs.",
            "Y",
        ),
        judge_fn=lambda _question, _context: False,
    )

    assert result.supported is True
    assert result.trace["mode"] == "builder"
    assert result.trace["answer_path"] == "best_effort"
    assert "Read more:" in result.answer
    assert "https://docs.example.com/retries" in result.answer
    assert [source.url for source in result.sources] == ["https://docs.example.com/retries"]


def test_golden_thresholded_query_filters_low_signal_chunks():
    result = run_query_case(
        results_by_query={
            "retry threshold": [
                {
                    "id": "hi",
                    "url": "https://docs.example.com/high",
                    "text": "High confidence retry policy details.",
                    "hierarchy": ["Reliability"],
                    "score": 0.91,
                },
                {
                    "id": "lo",
                    "url": "https://docs.example.com/low",
                    "text": "Low confidence unrelated snippet.",
                    "hierarchy": ["Misc"],
                    "score": 0.21,
                },
            ]
        },
        question="retry threshold",
        retrieval_mode="classic",
        enable_hybrid=False,
        enable_rewrite=False,
        enable_graph_expansion=False,
        enable_section_expansion=False,
        score_threshold=0.8,
        answer_fn=lambda _question, _context: "Thresholded answer",
        judge_fn=lambda _question, context: "high confidence retry policy" in context.lower(),
    )

    assert result.supported is True
    assert result.answer == "Thresholded answer"
    assert [source.url for source in result.sources] == ["https://docs.example.com/high"]
    assert result.trace["answer_path"] == "answerable_initial"


def test_golden_no_results_returns_hard_fallback():
    result = run_query_case(
        results_by_query={},
        question="What is the retention policy?",
        retrieval_mode="classic",
        enable_hybrid=False,
        enable_rewrite=False,
        enable_graph_expansion=False,
        enable_section_expansion=False,
    )

    assert result.supported is False
    assert "couldn't find anything" in result.answer.lower()
    assert result.sources == []
    assert result.trace["initial_result_count"] == 0
