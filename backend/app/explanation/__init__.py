"""Phase 6 hybrid explanation: rule-based (always) + optional LLM, both grounding-validated against the facts."""
from __future__ import annotations

from app.chess_core import Position

from .facts import build_facts
from .grounding import validate
from .llm import LLMUnavailable, llm_explain
from .rules import rule_based

MAX_REJECTED_SHARE = 0.5  # LLM output with more invalid sentences than this is discarded entirely


def explain_move(pos: Position, analysis: dict, move: str | None = None, use_llm: bool = False,
                 language: str = "English", client=None) -> dict:
    facts = build_facts(pos, analysis, move)
    rule = rule_based(facts)
    rule_check = validate(rule, facts)
    out = {"move": facts[0]["uci"], "san": facts[0]["san"], "source": "rule_based", "model": None,
           "language": "English", **rule_check["explanation"], "facts": facts,
           "grounding": {"valid": rule_check["valid"], "checked": rule_check["checked"],
                         "rejected": rule_check["rejected"], "fallback_reason": None}}
    if not use_llm:
        return out
    try:
        llm, meta = llm_explain(facts, language, client)
    except LLMUnavailable as e:
        out["grounding"]["fallback_reason"] = f"LLM unavailable: {e}"
        return out
    check = validate(llm, facts)
    share = len(check["rejected"]) / max(check["checked"], 1)
    if not check["summary_valid"] or share > MAX_REJECTED_SHARE:
        out["grounding"]["fallback_reason"] = "LLM output failed grounding"
        out["grounding"]["llm_rejected"] = check["rejected"]
        return out
    return {**out, "source": "llm", "model": meta["model"], "language": language, **check["explanation"],
            "llm": meta, "grounding": {"valid": check["valid"], "checked": check["checked"],
                                       "rejected": check["rejected"], "fallback_reason": None}}


__all__ = ["LLMUnavailable", "build_facts", "explain_move", "rule_based", "validate"]
