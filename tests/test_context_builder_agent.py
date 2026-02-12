from chatbot.context_builder_agent import ContextBuilderAgent


class DummyPlannerLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def generate(self, _prompt: str) -> str:
        if not self._responses:
            return "{}"
        return self._responses.pop(0)


def test_context_builder_uses_llm_for_concepts_and_followups():
    planner = DummyPlannerLLM(
        responses=[
            '{"concepts": ["aliases", "json serialization"]}',
            '{"queries": ["pydantic aliases json serialization"], "drop_chunk_ids": ["chunk-2"]}',
        ]
    )
    agent = ContextBuilderAgent(planner_llm=planner)

    concepts = agent.extract_concepts("How do aliases interact with JSON serialization in Pydantic?")
    assert concepts == ["aliases", "json serialization"]

    results = [{"id": "chunk-1", "text": "Validation and validators are core pydantic concepts."}]
    coverage = agent.coverage_report(concepts, results)
    assert coverage["missing"] == ["aliases", "json serialization"]

    decision = agent.decide_followups(
        "How do aliases interact with JSON serialization in Pydantic?",
        coverage["missing"],
        results,
    )
    assert decision["queries"] == ["pydantic aliases json serialization"]
    assert decision["drop_chunk_ids"] == ["chunk-2"]


def test_context_builder_initial_route_from_llm():
    route_json = (
        '{"mode":"retrieve_followup","standalone_query":"pydantic aliases json serialize behavior",'
        '"concepts":["aliases","serialization"]}'
    )
    planner = DummyPlannerLLM(
        responses=[
            route_json
        ]
    )
    agent = ContextBuilderAgent(planner_llm=planner)

    route = agent.plan_initial_route(
        question="How does it serialize aliases?",
        memory_context="User: We discussed alias usage in pydantic models.",
    )
    assert route["mode"] == "retrieve_followup"
    assert route["standalone_query"] == "pydantic aliases json serialize behavior"
    assert route["concepts"] == ["aliases", "serialization"]
