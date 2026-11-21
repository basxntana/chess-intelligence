"""Stage 3: grounding validation. Checks each sentence against the facts it cites (and the fact set overall):
  - cites at least one existing fact id
  - every move it names (SAN or UCI) is a move present in the facts
  - every square it names appears in the facts
  - decimal evaluations / "mate in N" match a fact value
  - tactical motif words (fork, pin, ...) are backed by a cited fact with that motif
  - mate/checkmate and "wins material" claims are backed by cited facts
  - no guarantee language about hypothetical lines
"""
from __future__ import annotations

import re

SAN_RE = re.compile(r"(?<![\w-])(O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](?:=[QRBN])?)[+#]?(?![\w])")
UCI_RE = re.compile(r"(?<![\w])([a-h][1-8][a-h][1-8][qrbn]?)(?![\w])")
SQUARE_RE = re.compile(r"(?<![\w])([a-h][1-8])(?![\w])")
DECIMAL_RE = re.compile(r"(?<![\w.])([+\-−]?\d+\.\d+)(?!\w|\.\d)")  # a sentence-ending period still matches
MATE_IN_RE = re.compile(r"(?:mate in|mat dalam) (\d+)", re.IGNORECASE)
# English terms plus Indonesian equivalents, so a translated explanation cannot slip a motif past the check.
MOTIF_WORDS = {
    "fork": r"\b(fork(s|ed|ing)?|garpu)\b",
    "pin": r"\b(pin(s|ned|ning)?|sematan|terpin|di-?pin)\b",
    "skewer": r"\b(skewer(s|ed|ing)?|tusuk sate)\b",
    "discovered_attack": r"\b(discovered|tersingkap)\b",
    "double_attack": r"\b(double attack|serangan ganda)",
    "hanging_piece": r"\b(hanging|en prise|undefended|tak terjaga|tidak terjaga|menggantung)\b",
}
MATE_WORDS = re.compile(r"\b(check)?mat(e|es|ing)\b|\bskak ?mat\b|\bmat\b", re.IGNORECASE)
WINS_MATERIAL = re.compile(r"\b(win(s|ning)?|menang(kan)?|merebut)\b[^.]*"
                           r"\b(material|materi|pawn|pion|knight|kuda|bishop|gajah|rook|benteng|queen|ratu|exchange)\b",
                           re.IGNORECASE)
GUARANTEE = re.compile(r"\b(guarantee[sd]?|always wins|forced win|cannot be stopped|unstoppable|pasti menang|dijamin)\b",
                       re.IGNORECASE)
MATE_MOTIFS = {"checkmate", "checkmate_threat"}


def _walk(obj, out: set[str]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, out)
    elif isinstance(obj, str):
        out.add(obj)


def allowed_tokens(facts: list[dict]) -> dict:
    strings: set[str] = set()
    _walk(facts, strings)
    moves = {s.rstrip("+#") for s in strings if SAN_RE.fullmatch(s) or UCI_RE.fullmatch(s)}
    squares = {m.group(1) for s in strings for m in SQUARE_RE.finditer(s)}
    squares |= {s[:2] for s in strings if UCI_RE.fullmatch(s)} | {s[2:4] for s in strings if UCI_RE.fullmatch(s)}
    numbers: set[float] = set()
    for s in strings:
        for m in DECIMAL_RE.finditer(s):
            numbers.add(round(float(m.group(1).replace("−", "-")), 2))
    for f in facts:
        for key in ("material_gain",):
            if isinstance(f.get(key), int) and f[key] < 50_000:
                numbers.add(round(f[key] / 100, 1))
    mates = {abs(f["mate_in"]) for f in facts if f.get("mate_in")}
    return {"moves": moves, "squares": squares, "numbers": numbers, "mates": mates}


def check_sentence(sent: dict, facts_by_id: dict, allowed: dict) -> list[str]:
    text, cited = sent.get("text", ""), sent.get("facts", [])
    issues = []
    if not cited:
        issues.append("cites no facts")
    unknown = [c for c in cited if c not in facts_by_id]
    if unknown:
        issues.append(f"cites unknown facts {unknown}")
    cited_facts = [facts_by_id[c] for c in cited if c in facts_by_id]
    cited_motifs = {f.get("motif") for f in cited_facts}

    for m in SAN_RE.finditer(text):
        if m.group(1) not in allowed["moves"]:
            issues.append(f"names move {m.group(1)} not in the facts")
    for m in UCI_RE.finditer(text):
        if m.group(1) not in allowed["moves"]:
            issues.append(f"names move {m.group(1)} not in the facts")
    for m in SQUARE_RE.finditer(text):
        if m.group(1) not in allowed["squares"]:
            issues.append(f"names square {m.group(1)} not in the facts")
    for m in DECIMAL_RE.finditer(text):
        raw = m.group(1).replace("−", "-")
        v = round(float(raw), 2)
        signed = raw[0] in "+-"  # an explicit sign must match; an unsigned number may quote a magnitude
        if not any(abs(v - n) <= 0.051 if signed else abs(v - abs(n)) <= 0.051 for n in allowed["numbers"]):
            issues.append(f"number {m.group(1)} does not match any fact")
    for m in MATE_IN_RE.finditer(text):
        if int(m.group(1)) not in allowed["mates"]:
            issues.append(f"claims mate in {m.group(1)} without engine support")
    for motif, pattern in MOTIF_WORDS.items():
        if re.search(pattern, text, re.IGNORECASE) and motif not in cited_motifs:
            issues.append(f"mentions {motif} without citing a {motif} fact")
    if MATE_WORDS.search(text) and not (cited_motifs & MATE_MOTIFS or any(f.get("mate_in") for f in cited_facts)):
        issues.append("mentions mate without citing a mate fact")
    if WINS_MATERIAL.search(text) and not any((f.get("material_gain") or 0) >= 100 or
                                              f.get("type") == "threat_before_move" for f in cited_facts):
        issues.append("claims winning material without citing a material gain")
    if GUARANTEE.search(text) and not any(f.get("mate_in") for f in cited_facts):
        issues.append("presents a variation as guaranteed")
    return issues


SECTIONS = ("details", "tactical_warnings", "strategic_summary", "candidate_comparison")


def validate(explanation: dict, facts: list[dict]) -> dict:
    """Returns {valid, checked, rejected: [{section, text, issues}], explanation (invalid sentences removed)}."""
    by_id = {f["id"]: f for f in facts}
    allowed = allowed_tokens(facts)
    rejected, checked, clean = [], 0, {}
    summary_issues = check_sentence(explanation.get("summary") or {}, by_id, allowed)
    checked += 1
    if summary_issues:
        rejected.append({"section": "summary", "text": (explanation.get("summary") or {}).get("text"),
                         "issues": summary_issues})
    clean["summary"] = explanation.get("summary")
    for section in SECTIONS:
        kept = []
        for s in explanation.get(section) or []:
            checked += 1
            issues = check_sentence(s, by_id, allowed)
            if issues:
                rejected.append({"section": section, "text": s.get("text"), "issues": issues})
            else:
                kept.append(s)
        clean[section] = kept
    # The summary must name the selected move.
    move_san = by_id["move"]["san"].rstrip("+#")
    summary_text = (explanation.get("summary") or {}).get("text", "")
    if move_san not in summary_text and by_id["move"]["uci"] not in summary_text:
        summary_issues.append("summary does not name the selected move")
        rejected.append({"section": "summary", "text": summary_text, "issues": ["does not name the selected move"]})
    return {"valid": not rejected, "summary_valid": not summary_issues, "checked": checked, "rejected": rejected,
            "explanation": clean}
