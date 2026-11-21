"""Stage 2: natural-language explanation by Claude, constrained to the verified facts.
The model returns JSON (structured outputs) in the same shape as the rule-based explanation, citing fact ids
per sentence; grounding.validate() then checks every sentence before anything reaches the user."""
from __future__ import annotations

import json

import anthropic

from app.config import settings

SENTENCE = {"type": "object", "properties": {"text": {"type": "string"},
                                             "facts": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "facts"], "additionalProperties": False}
SCHEMA = {
    "type": "object",
    "properties": {
        "summary": SENTENCE,
        "details": {"type": "array", "items": SENTENCE},
        "tactical_warnings": {"type": "array", "items": SENTENCE},
        "strategic_summary": {"type": "array", "items": SENTENCE},
        "candidate_comparison": {"type": "array", "items": SENTENCE},
    },
    "required": ["summary", "details", "tactical_warnings", "strategic_summary", "candidate_comparison"],
    "additionalProperties": False,
}

SYSTEM = """You explain a chess engine's recommendation to a club player, using only a list of verified facts.

The facts come from a chess engine and a position analyser; they are the only source of truth. Each fact has an id.

How to write:
- Explain why the move in the "move" fact is recommended: what it achieves tactically and strategically, which threats it meets, and how the alternatives compare.
- Every sentence goes in exactly one section and lists, in "facts", the ids of the facts it relies on. A sentence with nothing to cite should not be written.
- Name moves exactly as they appear in the facts (SAN such as Nf3, Bxc7+, O-O). Name only squares, moves, numbers and tactical motifs that appear in the facts you cite. If the facts do not support a claim, leave it out; an explanation that says less is better than one that guesses.
- Quote evaluations as given in the facts (e.g. "+0.52"); they are in pawns from the perspective stated in the fact.
- The principal variation is the engine's expected best play, not a guaranteed outcome; describe it that way.
- Mention mate only when a cited fact has mate_in or a checkmate / checkmate_threat motif.
- Use tactical terms (fork, pin, skewer, discovered attack, double attack, hanging / en prise) only when you cite a fact with that motif. When writing in a language other than English, add the English term in parentheses, e.g. "garpu (fork)".
- The summary is one or two sentences and names the recommended move.
- Write plainly for a human reader; no fact ids, JSON keys or engine jargon in the text itself.
- Write in {language}."""


class LLMUnavailable(Exception):
    pass


def llm_explain(facts: list[dict], language: str = "English", client: anthropic.Anthropic | None = None) -> tuple[dict, dict]:
    """Returns (explanation, metadata). Raises LLMUnavailable on refusal, truncation or API/credential errors."""
    try:
        client = client or anthropic.Anthropic()
        response = client.beta.messages.create(
            model=settings.llm_model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # a declined request is retried server-side on Anthropic's recommended model
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            system=SYSTEM.format(language=language),
            messages=[{"role": "user", "content": "Facts:\n" + json.dumps(facts, ensure_ascii=False)}],
        )
    except anthropic.AnthropicError as e:  # network, rate limits, 4xx/5xx: all mean "use rule-based"
        raise LLMUnavailable(f"{type(e).__name__}: {e}") from e
    except TypeError as e:  # the SDK reports missing credentials as a TypeError when the request is built
        if "authentication" not in str(e):
            raise
        raise LLMUnavailable("no Anthropic credentials configured (set ANTHROPIC_API_KEY)") from e
    if response.stop_reason == "refusal":
        raise LLMUnavailable(f"refusal ({getattr(response.stop_details, 'category', None)})")
    if response.stop_reason == "max_tokens":
        raise LLMUnavailable("response truncated (max_tokens)")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise LLMUnavailable("no text block in response")
    try:
        explanation = json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMUnavailable(f"invalid JSON: {e}") from e
    meta = {"model": response.model, "request_id": getattr(response, "_request_id", None),
            "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return explanation, meta
