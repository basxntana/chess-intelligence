"""Strategic feature extraction (TRD 3.3). Built on the evaluation's evidence so every feature carries the
centipawn weight the engine actually gave it. Each feature: category, feature, side, squares, score, evidence."""
from __future__ import annotations

from app.chess_core import Position
from app.evaluation import PIECE_VALUES, explain

# evaluation evidence feature -> strategic category
CATEGORY = {
    "center_attacks": "center_control",
    "doubled_pawns": "pawn_weakness", "isolated_pawn": "pawn_weakness", "pawn_islands": "pawn_weakness",
    "connected_pawn": "pawn_strength", "passed_pawn": "passed_pawn",
    "pawn_shield": "king_safety", "open_files_near_king": "king_safety", "king_zone_attacked": "king_safety",
    "bishop_pair": "piece_coordination", "rook_open_file": "open_file", "rook_semi_open_file": "open_file",
}
NAMES = {"p": "pawn", "n": "knight", "b": "bishop", "r": "rook", "q": "queen"}


def _feature(category, feature, side, squares, score, evidence=None) -> dict:
    return {"category": category, "feature": feature, "side": side, "squares": squares, "score": score,
            "evidence": evidence or {}}


def strategic_features(pos: Position, breakdown: dict | None = None) -> list[dict]:
    e = breakdown or explain(pos)
    phase_mg = e["phase"] / e["max_phase"]
    out = []
    mobility: dict[str, list] = {"white": [], "black": []}
    for f in e["features"]:
        score = round(f["mg"] * phase_mg + f["eg"] * (1 - phase_mg))
        if f["feature"] == "piece_mobility":
            mobility[f["side"]].append((f["squares"][0], f["detail"]["piece"], f["detail"]["moves"]))
        else:
            out.append(_feature(CATEGORY.get(f["feature"], f["term"]), f["feature"], f["side"], f["squares"], score,
                                f.get("detail")))
    out += _material(pos) + _activity(mobility) + _files(pos)
    return out


def _material(pos: Position) -> list[dict]:
    counts = {"white": dict.fromkeys("pnbrq", 0), "black": dict.fromkeys("pnbrq", 0)}
    for s, p in enumerate(pos.board):
        if p and p not in "Kk" and not s & 0x88:
            counts["white" if p.isupper() else "black"][p.lower()] += 1
    total = {side: sum(PIECE_VALUES[k] * n for k, n in c.items()) for side, c in counts.items()}
    diff = total["white"] - total["black"]
    out = [_feature("material", "material_balance", "white" if diff > 0 else "black" if diff < 0 else "both", [],
                    abs(diff), {"white": total["white"], "black": total["black"], "counts": counts})]
    minors = {s: c["n"] + c["b"] for s, c in counts.items()}
    for side, opp in (("white", "black"), ("black", "white")):
        c, o = counts[side], counts[opp]
        if c["r"] > o["r"] and minors[side] < minors[opp]:
            out.append(_feature("material", "exchange_up", side, [], 0, {"rooks": c["r"], "minors": minors[side]}))
        if c["q"] > o["q"] and c["r"] < o["r"]:
            out.append(_feature("material", "queen_vs_rooks", side, [], 0, {}))
        if minors[side] > minors[opp] and c["p"] < o["p"] and c["r"] == o["r"] and c["q"] == o["q"]:
            out.append(_feature("material", "piece_vs_pawns", side, [], 0,
                                {"extra_minors": minors[side] - minors[opp], "pawn_deficit": o["p"] - c["p"]}))
    return out


def _activity(mobility: dict[str, list]) -> list[dict]:
    out = []
    for side, pieces in mobility.items():
        if not pieces:
            continue
        total = sum(n for _, _, n in pieces)
        sq, k, n = min(pieces, key=lambda x: x[2])
        out.append(_feature("piece_activity", "mobility", side, [], total,
                            {"total_moves": total, "per_piece": [{"square": s, "piece": NAMES[p], "moves": m}
                                                                 for s, p, m in pieces]}))
        if n <= 2:
            out.append(_feature("piece_activity", "passive_piece", side, [sq], n, {"piece": NAMES[k], "moves": n}))
    return out


def _files(pos: Position) -> list[dict]:
    pawn_files = {"P": set(), "p": set()}
    for s, p in enumerate(pos.board):
        if p in ("P", "p") and not s & 0x88:
            pawn_files[p].add(s & 7)
    out = []
    for f in range(8):
        name = "abcdefgh"[f]
        w, b = f in pawn_files["P"], f in pawn_files["p"]
        if not w and not b:
            out.append(_feature("open_file", "open_file", "both", [], 0, {"file": name}))
        elif not w or not b:
            out.append(_feature("open_file", "semi_open_file", "white" if not w else "black", [], 0, {"file": name}))
    return out


def feature_changes(before: list[dict], after: list[dict]) -> dict:
    """Features that appear or disappear between two positions (ignores score-only drift)."""
    def key(f):
        return f["feature"], f["side"], tuple(f["squares"]), str(f["evidence"].get("file", ""))

    skip = {"mobility", "material_balance", "center_attacks", "king_zone_attacked"}  # always-present aggregates
    b = {key(f): f for f in before if f["feature"] not in skip}
    a = {key(f): f for f in after if f["feature"] not in skip}
    return {"gained": [a[k] for k in a.keys() - b.keys()], "lost": [b[k] for k in b.keys() - a.keys()]}

