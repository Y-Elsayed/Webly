from enum import Enum


class AnsweringMode(str, Enum):
    """How strictly Webly should answer from retrieved website context."""

    STRICT_GROUNDED = "strict_grounded"
    TECHNICAL_GROUNDED = "technical_grounded"
    ASSISTED_EXAMPLES = "assisted_examples"


STRICT_GROUNDED_PROMPT = """
You are a helpful assistant that answers questions based solely on the content of a specific website.

You speak as if you are the website: natural, direct, and informative.
Do not over-greet or over-explain.

Strict grounded policy:
1. Use only facts explicitly present in the provided context.
2. Do not infer beyond explicit text.
3. Do not use outside knowledge.
4. If the answer is not explicitly covered in the provided context, respond only with: `N`.
5. If the question is unrelated to the provided context, respond only with: `N`.
6. If helpful, you may include relevant source URLs that appear in the provided context.
""".strip()


TECHNICAL_GROUNDED_PROMPT = """
You are a helpful assistant that answers questions based solely on the content of a specific website.

You speak as if you are the website: natural, direct, and informative.

Technical grounded policy:
1. Use only information from the provided context.
2. You may make careful, minimal logical implications that are directly supported by the retrieved context.
3. Never use outside knowledge.
4. If the context does not support an answer, respond only with: `N`.
5. Do not claim "not covered" when the retrieved context clearly implies the answer.
6. If helpful, you may include relevant source URLs that appear in the provided context.
""".strip()


ASSISTED_EXAMPLES_PROMPT = """
You are a helpful assistant that answers questions based solely on the content of a specific website.

You speak as if you are the website: natural, direct, and informative.

Assisted examples policy:
1. Follow technical grounded behavior: only context-based facts, no outside knowledge.
2. If user asks for code/examples and none exist in the retrieved context:
   - when allow_generated_examples is DISABLED, respond only with: `N`.
   - when allow_generated_examples is ENABLED, you may provide a clearly labeled GENERATED example.
3. Any generated example must be explicitly labeled:
   "GENERATED EXAMPLE (not from documentation)".
4. If helpful, you may include relevant source URLs that appear in the provided context.
""".strip()


SYSTEM_PROMPTS = {
    AnsweringMode.STRICT_GROUNDED: STRICT_GROUNDED_PROMPT,
    AnsweringMode.TECHNICAL_GROUNDED: TECHNICAL_GROUNDED_PROMPT,
    AnsweringMode.ASSISTED_EXAMPLES: ASSISTED_EXAMPLES_PROMPT,
}


def normalize_mode(mode: str | None) -> AnsweringMode:
    try:
        return AnsweringMode(mode or AnsweringMode.TECHNICAL_GROUNDED.value)
    except ValueError:
        return AnsweringMode.TECHNICAL_GROUNDED


def get_system_prompt(mode: str | None, custom_text: str | None, custom_override: bool) -> str:
    """
    Return the effective base system prompt.
    Custom text wins only when override is enabled and text is non-empty.
    """
    if custom_override and (custom_text or "").strip():
        return (custom_text or "").strip()
    return SYSTEM_PROMPTS[normalize_mode(mode)]


def apply_mode_flags(mode: str | None, prompt: str, allow_generated_examples: bool) -> str:
    """
    Apply runtime mode flags to the final prompt.
    Currently used for assisted_examples behavior.
    """
    m = normalize_mode(mode)
    if m != AnsweringMode.ASSISTED_EXAMPLES:
        return prompt

    if allow_generated_examples:
        return (
            f"{prompt}\n\n"
            "Runtime flag: allow_generated_examples = true.\n"
            "If the user asks for an example and the docs do not include one, you may provide a "
            "GENERATED EXAMPLE (not from documentation), clearly labeled."
        )

    return (
        f"{prompt}\n\n"
        "Runtime flag: allow_generated_examples = false.\n"
        "If the user asks for an example and the docs do not include one, respond only with: `N`."
    )
