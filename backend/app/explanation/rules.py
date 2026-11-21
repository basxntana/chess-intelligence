"""Stage 1: rule-based explanation. Every sentence is a template filled from facts and cites their ids."""
from __future__ import annotations

from .facts import piece_name

TERM_NAMES = {"pst": "piece placement", "mobility": "piece mobility", "center_control": "central control",
              "pawn_structure": "pawn structure", "king_safety": "king safety",
              "piece_coordination": "piece coordination"}
FEATURE_NAMES = {
    "passed_pawn": "a passed pawn", "isolated_pawn": "an isolated pawn", "doubled_pawns": "doubled pawns",
    "bishop_pair": "the bishop pair", "rook_open_file": "a rook on an open file",
    "rook_semi_open_file": "a rook on a semi-open file", "pawn_shield": "a pawn shield in front of the king",
    "open_files_near_king": "open files near the king", "passive_piece": "a passive piece",
    "exchange_up": "an exchange advantage", "piece_vs_pawns": "a piece against pawns",
    "queen_vs_rooks": "a queen against rooks",
}


def sentence(text: str, *fact_ids: str) -> dict:
    return {"text": text, "facts": list(fact_ids)}


def _squares(sqs: list[str]) -> str:
    return sqs[0] if len(sqs) == 1 else ", ".join(sqs[:-1]) + " and " + sqs[-1]


def _eval_phrase(ev: dict) -> str:
    if ev["mate_in"] is not None:
        return f"forced mate in {ev['mate_in']}" if ev["mate_in"] > 0 else f"being mated in {-ev['mate_in']}"
    return f"an evaluation of {ev['pawns']} pawns for {ev['perspective'].capitalize()}"


def _tactic_sentence(f: dict, move_san: str) -> str | None:
    e, motif = f["evidence"], f["motif"]
    gain = f.get("material_gain")
    wins = f" The engine line wins about {gain / 100:.1f} pawns of material." if gain and gain < 50_000 else ""
    if motif == "checkmate":
        return f"{move_san} is checkmate."
    if motif == "check":
        return f"{move_san} gives check."
    if motif == "fork":
        targets = [f"the {piece_name(p)} on {s}" for p, s in zip(e["target_pieces"], e["targets"], strict=True)]
        return f"The {piece_name(e['piece'])} on {e['from']} forks {_squares(targets)}.{wins}"
    if motif == "pin":
        kind = "king" if e.get("absolute") else piece_name(e["pieces"][2])
        return (f"It pins the {piece_name(e['pieces'][1])} on {e['front']} to the {kind} on {e['behind']} "
                f"(attacker on {e['attacker']}).")
    if motif == "skewer":
        return (f"It skewers the {piece_name(e['pieces'][1])} on {e['front']}: once it moves, the "
                f"{piece_name(e['pieces'][2])} on {e['behind']} can be taken.{wins}")
    if motif == "discovered_attack":
        hits = [f"the {piece_name(u['piece'])} on {u['target']} (from {u['attacker']})" for u in e["uncovered"]]
        kind = "discovered check" if e.get("check") else "discovered attack"
        return f"Moving the {piece_name(e['moved_piece'])} unleashes a {kind} on {_squares(hits)}.{wins}"
    if motif == "double_attack":
        hits = [f"the {piece_name(t['piece'])} on {t['square']}" for t in e["targets"]]
        return f"It creates a double attack on {_squares(hits)}.{wins}"
    if motif == "checkmate_threat":
        return f"It threatens mate with {' or '.join(e['mating_moves_san'])}."
    if motif == "hanging_piece" and f["against"] == f.get("_mover"):
        return (f"Note that it leaves the {piece_name(e['piece'])} on {f['squares'][0]} en prise "
                f"(attacked by {_squares(e['attackers'])}).")
    if motif == "material_gain":
        return f"The engine line wins about {gain / 100:.1f} pawns of material." if gain and gain < 50_000 else None
    return None


def rule_based(facts: list[dict]) -> dict:
    by_id = {f["id"]: f for f in facts}
    mv, ev = by_id["move"], by_id["eval"]
    who = "the engine's choice" if mv["best"] else "a candidate move"
    summary = sentence(f"{mv['san']} is {who} at depth {ev['depth']}, with {_eval_phrase(ev)}.", "move", "eval")

    details = []
    if len(mv["pv_san"]) > 1:
        details.append(sentence(f"The expected continuation is {' '.join(mv['pv_san'])}.", "move"))
    for f in facts:
        if f["type"] == "tactic":
            text = _tactic_sentence({**f, "_mover": mv["side"]}, mv["san"])
            if text and f["motif"] != "hanging_piece":
                details.append(sentence(text, f["id"]))

    warnings = []
    for f in facts:
        if f["type"] == "tactic" and f["motif"] == "hanging_piece":
            warnings.append(sentence(_tactic_sentence({**f, "_mover": mv["side"]}, mv["san"]), f["id"]))
        elif f["type"] == "threat_before_move":
            by = f["by"].capitalize()
            if f["motif"] == "hanging_piece":
                what = f"{by} was threatening to win the {piece_name(f['evidence'].get('piece'))} on {f['squares'][0]}"
            elif f["motif"] == "checkmate_threat":
                what = f"{by} was threatening mate"
            else:
                what = f"{by} had a {f['motif']} on {_squares(f['squares'])}"
            status = "this move deals with it" if f["resolved_by_move"] else "it remains after this move"
            warnings.append(sentence(f"{what}; {status}.", f["id"]))

    strategic = []
    for f in facts:
        if f["type"] == "strategic_change":
            name = FEATURE_NAMES.get(f["feature"], f["feature"].replace("_", " "))
            where = f" on {_squares(f['squares'])}" if f["squares"] else ""
            verb = "now has" if f["change"] == "gained" else "no longer has"
            strategic.append(sentence(f"{f['side'].capitalize()} {verb} {name}{where}.", f["id"]))
        elif f["type"] == "eval_term_change":
            direction = "improves" if f["delta_cp"] > 0 else "worsens"
            strategic.append(sentence(f"Statically, it {direction} {TERM_NAMES.get(f['term'], f['term'])} "
                                      f"({f['pawns']}).", f["id"]))

    comparison = []
    for f in facts:
        if f["type"] == "alternative":
            score = f"mate in {f['mate_in']}" if f["mate_in"] is not None else f"{f['pawns']}"
            if f["difference_cp"] is None:
                rel = "better" if f["better"] else "worse"
            else:
                rel = "about equal" if abs(f["difference_cp"]) < 10 else f"{f['difference_pawns']} relative"
            comparison.append(sentence(f"{f['san']} scores {score} ({rel}).", f["id"]))

    return {"summary": summary, "details": details, "tactical_warnings": warnings,
            "strategic_summary": strategic, "candidate_comparison": comparison}
