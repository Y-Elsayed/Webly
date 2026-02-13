from chatbot.prompts.system_prompts import (
    AnsweringMode,
    apply_mode_flags,
    get_system_prompt,
)


def test_get_system_prompt_uses_override_when_non_empty():
    prompt = get_system_prompt(AnsweringMode.STRICT_GROUNDED.value, "CUSTOM", True)
    assert prompt == "CUSTOM"


def test_get_system_prompt_falls_back_to_mode_default_when_override_empty():
    prompt = get_system_prompt(AnsweringMode.TECHNICAL_GROUNDED.value, "", True)
    assert "Technical grounded policy" in prompt


def test_apply_mode_flags_only_changes_assisted_mode():
    base = get_system_prompt(AnsweringMode.STRICT_GROUNDED.value, "", False)
    flagged = apply_mode_flags(AnsweringMode.STRICT_GROUNDED.value, base, True)
    assert flagged == base

    assisted = get_system_prompt(AnsweringMode.ASSISTED_EXAMPLES.value, "", False)
    assisted_flagged = apply_mode_flags(AnsweringMode.ASSISTED_EXAMPLES.value, assisted, True)
    assert "allow_generated_examples = true" in assisted_flagged
