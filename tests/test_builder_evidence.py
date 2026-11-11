import json

import pytest

from tests.query_eval_harness import ScriptedChatAgent, ScriptedPlanner
from webly.chatbot.context_builder_agent import ContextBuilderAgent
from webly.pipeline.query_pipeline import QueryPipeline


def chunk(sid, text, **kwargs):
    return {"id": sid, "url": "https://example.test/admissions", "text": text, **kwargs}


def supported(index, sid, span, status="supported"):
    return {
        "requirement_index": index, "status": status,
        "evidence": [{"segment_id": sid, "supporting_span": span}],
    }


def pipeline(results, planner=None, **kwargs):
    agent = ScriptedChatAgent(results_by_query=results, planner=planner)
    return QueryPipeline(chat_agent=agent, enable_hybrid=False, **kwargs)


class RecordingPlanner:
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return json.dumps(self.payload)


@pytest.mark.parametrize("text,requirement", [
    ("Tuition costs 500 dollars.", "How much are the fees?"),
    ("Applications are not accepted after June.", "Can I apply in July?"),
])
def test_semantic_assessment_uses_evidence_without_literal_concept_gate(text, requirement):
    planner = ScriptedPlanner(
        route_payload={"mode": "retrieve_new", "concepts": ["fees"], "requirements": [requirement]},
        assessment_payloads=[{"coverage": [supported(0, "fee", text)], "queries": ["unnecessary"]}],
    )
    result = pipeline({requirement: [chunk("fee", text)]}, planner).query_result(requirement)
    assert result.trace["stop_reason"] == "sufficient_evidence"
    assert result.trace["search_count"] == 1
    assert result.trace["coverage"]["covered"] == [requirement]


def test_topic_mention_is_missing_and_structural_search_recovers_amount():
    question = "How much are the fees?"
    fee = "Tuition costs 500 dollars."
    planner = ScriptedPlanner(
        route_payload={"mode": "retrieve_new", "requirements": [question]},
        assessment_payloads=[
            {"coverage": [], "queries": ["tuition costs"]},
            {"coverage": [supported(0, "fee", fee)], "queries": []},
        ],
    )
    qp = pipeline({question: [chunk("intro", "See our fees page.")], "tuition costs": [chunk("fee", fee)]}, planner)
    result = qp.query_result(question)
    assert result.trace["executed_queries"] == [question, "tuition costs"]
    assert result.trace["assessments"][0]["coverage"][0]["status"] == "missing"
    assert result.trace["requirement_coverage"][0]["status"] == "supported"
    assert result.trace["new_evidence_counts"] == [1]


def test_multipart_evidence_preserves_multiple_segments_from_one_page():
    requirements = ["What does tuition cost?", "When is the deadline?"]
    planner = ScriptedPlanner(
        route_payload={"mode": "retrieve_new", "requirements": requirements},
        assessment_payloads=[{
            "coverage": [supported(0, "fee", "500 dollars"), supported(1, "date", "June 1")], "queries": [],
        }],
    )
    qp = pipeline({"root": [chunk("fee", "Tuition: 500 dollars"), chunk("date", "Deadline: June 1")]}, planner)
    result = qp.query_result("root")
    assert result.trace["coverage"]["covered"] == requirements
    assert {source.chunk_id for source in result.sources} == {"fee", "date"}


@pytest.mark.parametrize("sid,span", [
    ("invented", "Visible text"), ("visible", "not in the source"), ("hidden", "Hidden text"),
    ("visible", "Hidden text"),
])
def test_assessment_rejects_unknown_ids_and_unshown_excerpts(sid, span):
    llm = RecordingPlanner({"coverage": [supported(0, sid, span)], "queries": []})
    builder = ContextBuilderAgent(llm)
    decision = builder.assess_evidence(
        "root", ["root"], "Visible text",
        {"visible": {"original_text": "Visible text and Hidden text", "supplied_text": "Visible text"}},
        {}, [],
    )
    assert decision["coverage"][0]["status"] == "missing"
    assert decision["coverage"][0]["evidence"] == []


def test_trimmed_text_cannot_count_as_support_even_when_in_original():
    original = "Visible text. " + "padding " * 100 + "Secret amount: 500 dollars."
    llm = RecordingPlanner({"coverage": [supported(0, "visible", "Secret amount: 500 dollars.")], "queries": []})
    qp = pipeline({"root": [chunk("visible", original)]}, builder_max_rounds=0, max_context_chars=140)
    qp.context_builder = ContextBuilderAgent(llm)
    result = qp.query_result("root")
    assert "Secret amount" not in llm.prompts[-1]
    assert result.trace["requirement_coverage"][0]["status"] == "missing"


def test_same_excerpt_in_different_shown_chunk_does_not_validate_wrong_id():
    original = "Visible text. " + "padding " * 100 + "Secret amount: 500 dollars."
    qp = pipeline({"root": [chunk("a", original), chunk("b", "Secret amount: 500 dollars.")]})
    records = {"a": {"original_text": original}, "b": {"original_text": "Secret amount: 500 dollars."}}
    context = (
        "[Evidence: a] (Source: https://example.test/a)\nVisible text.\n\n---\n\n"
        "[Evidence: b] (Source: https://example.test/b)\nSecret amount: 500 dollars."
    )
    sources = [{"chunk_id": "a", "url": "https://example.test/a"}, {"chunk_id": "b", "url": "https://example.test/b"}]
    evidence = qp.context_tools.supplied_evidence(context, sources, records)
    builder = ContextBuilderAgent(RecordingPlanner({
        "coverage": [supported(0, "a", "Secret amount: 500 dollars.")], "queries": [],
    }))
    assert builder.assess_evidence("root", ["root"], context, evidence, {}, [])["coverage"][0]["status"] == "missing"


@pytest.mark.parametrize("graph,sections", [(True, True), (True, False), (False, True), (False, False)])
def test_structural_hints_respect_flags_and_do_not_trigger_automatic_searches(graph, sections):
    qp = pipeline({"root": [chunk(
        "seed", "Information", hierarchy=["Admissions", "Fees"],
        metadata={"incoming_links": [{"anchor_text": "Tuition pricing"}]},
    )]}, enable_graph_expansion=graph, enable_section_expansion=sections)
    llm = RecordingPlanner({"coverage": [], "queries": []})
    qp.context_builder = ContextBuilderAgent(llm)
    result = qp.query_result("root")
    prompt = llm.prompts[-1]
    hint_data = json.loads(prompt.split("Structural hints: ")[1].split("\n")[0])
    assert hint_data["anchors"] == (["Tuition pricing"] if graph else [])
    assert hint_data["headings"] == (["Admissions > Fees"] if sections else [])
    assert result.trace["search_count"] == 1
    assert result.trace["capabilities"]["graph_expansion"] is graph
    assert result.trace["expansion_strategy"] == "planner_guided"


def test_empty_initial_search_can_be_rescued_without_recrawling():
    planner = ScriptedPlanner(followup_payload={"queries": ["alternate"], "drop_chunk_ids": []})
    result = pipeline({"alternate": [chunk("fee", "Tuition: 500 dollars")]}, planner).query_result("root")
    assert result.trace["initial_result_count"] == 0
    assert result.trace["executed_queries"] == ["root", "alternate"]
    assert result.supported


def test_recrawl_search_shares_budget_with_deduplicated_followups():
    recrawls = []
    planner = ScriptedPlanner(
        assessment_payloads=[
            {"coverage": [], "queries": [" ROOT ", " next   query ", "NEXT QUERY"]},
            {"coverage": [], "queries": ["last", "over budget"]},
        ],
    )
    qp = pipeline({"next query": [chunk("seed", "Information")]}, planner,
                  recrawl_fn=lambda: recrawls.append(True), builder_max_rounds=4)
    result = qp.query_result("root", retry_on_empty=True)
    assert recrawls == [True]
    assert result.trace["executed_queries"] == ["root", "root", "next query", "last"]
    assert result.trace["search_count"] == 4


def test_no_new_segments_stops_even_with_more_rounds_and_new_queries():
    seed = chunk("seed", "Information")
    planner = ScriptedPlanner(assessment_payloads=[
        {"coverage": [], "queries": ["next"]}, {"coverage": [], "queries": ["unnecessary"]},
    ])
    result = pipeline({"root": [seed], "next": [seed]}, planner, builder_max_rounds=3).query_result("root")
    assert result.trace["executed_queries"] == ["root", "next"]
    assert result.trace["new_evidence_counts"] == [0]
    assert result.trace["stop_reason"] == "no_new_evidence"


def test_search_budget_is_global_and_final_coverage_uses_last_results():
    planner = ScriptedPlanner(assessment_payloads=[
        {"coverage": [], "queries": ["one", "two", "three"]},
        {"coverage": [supported(0, "three", "Last result", status="partial")], "queries": ["four"]},
    ])
    result = pipeline({
        "root": [chunk("seed", "Information")],
        "one": [chunk("one", "First result")],
        "two": [chunk("two", "Second result")],
        "three": [chunk("three", "Last result")],
    }, planner, builder_max_rounds=5).query_result("root")
    assert result.trace["executed_queries"] == ["root", "one", "two", "three"]
    assert result.trace["stop_reason"] == "search_budget"
    assert result.trace["requirement_coverage"][0]["status"] == "partial"
    assert result.trace["coverage"]["missing"] == ["root"]


def test_only_previously_tried_queries_stop_without_more_searches():
    planner = ScriptedPlanner(followup_payload={"queries": [" ROOT  "], "drop_chunk_ids": []})
    result = pipeline({"root": [chunk("seed", "Information")]}, planner).query_result("root")
    assert result.trace["search_count"] == 1
    assert result.trace["stop_reason"] == "no_new_queries"


def test_followup_uses_standalone_query_but_new_question_ignores_memory():
    followup = ScriptedPlanner(route_payload={
        "mode": "retrieve_followup", "standalone_query": "Course tuition", "requirements": [],
    })
    qp = pipeline({"Course tuition": [chunk("fee", "500 dollars")]}, followup)
    result = qp.query_result("How much does it cost?", memory_context="The course is biology.")
    assert result.trace["executed_queries"] == ["Course tuition"]
    assert result.trace["requirements"] == ["Course tuition"]
    qp = pipeline({"New topic": [chunk("other", "New information")]})
    result = qp.query_result("New topic", memory_context="Unrelated old conversation")
    assert result.trace["executed_queries"] == ["New topic"]


def test_zero_rounds_still_assesses_but_never_runs_followup_searches():
    planner = ScriptedPlanner(followup_payload={"queries": ["next"], "drop_chunk_ids": []})
    result = pipeline({"root": [chunk("seed", "Information")]}, planner, builder_max_rounds=0).query_result("root")
    assert len(result.trace["assessments"]) == 1
    assert result.trace["executed_queries"] == ["root"]
    assert result.trace["stop_reason"] == "round_limit"


@pytest.mark.parametrize("payload", [[], {"coverage": "wrong", "queries": []},
    {"coverage": [{"requirement_index": 0, "status": [], "evidence": []}], "queries": []},
    {"coverage": [], "queries": [], "drop_chunk_ids": ["seed"]},
])
def test_malformed_assessment_keeps_evidence_and_uses_existing_answer_path(payload):
    qp = pipeline({"root": [chunk("seed", "Information")]})
    qp.context_builder = ContextBuilderAgent(RecordingPlanner(payload))
    result = qp.query_result("root")
    assert result.trace["stop_reason"] == "invalid_assessment"
    assert result.trace["search_count"] == 1
    assert [source.chunk_id for source in result.sources] == ["seed"]


def test_planner_exception_during_routing_and_assessment_preserves_evidence():
    class FailedPlanner:
        def generate(self, prompt):
            raise RuntimeError("Provider unavailable")

    qp = pipeline({"root": [chunk("seed", "Information")]})
    qp.context_builder = ContextBuilderAgent(FailedPlanner())
    result = qp.query_result("root")
    assert result.trace["stop_reason"] == "planner_failure"
    assert result.trace["requirements"] == ["root"]
    assert result.sources


def test_assessment_prompt_budget_prevents_model_call():
    llm = RecordingPlanner({"coverage": [], "queries": []})
    builder = ContextBuilderAgent(llm)
    decision = builder.assess_evidence("root", ["root"], "Arabic: " + "ع" * 2000, {}, {}, [], max_total_tokens=4096)
    assert decision["error"] == "prompt_budget"
    assert llm.prompts == []


def test_deadline_prevents_new_searches_and_reassessment(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("webly.pipeline.query_pipeline.time.monotonic", lambda: clock[0])
    qp = pipeline({"root": [chunk("seed", "Information")]})
    planner = RecordingPlanner({"coverage": [], "queries": ["next"]})
    qp.context_builder = ContextBuilderAgent(planner)
    original_search = qp._search

    def slow_search(*args, **kwargs):
        results = original_search(*args, **kwargs)
        clock[0] = 31.0
        return results

    qp._search = slow_search
    result = qp.query_result("root")
    assert result.trace["stop_reason"] == "deadline"
    assert result.trace["executed_queries"] == ["root"]
    assert len(planner.prompts) == 1  # Initial routing only.
    assert result.sources


def test_planner_exceeding_deadline_cannot_schedule_followup(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("webly.pipeline.query_pipeline.time.monotonic", lambda: clock[0])

    class SlowPlanner(RecordingPlanner):
        def generate(self, prompt):
            if "Task: assess evidence" in prompt:
                clock[0] = 31.0
            return super().generate(prompt)

    qp = pipeline({"root": [chunk("seed", "Information")]})
    qp.context_builder = ContextBuilderAgent(SlowPlanner({"coverage": [], "queries": ["next"]}))
    result = qp.query_result("root")
    assert result.trace["stop_reason"] == "deadline"
    assert result.trace["search_count"] == 1
