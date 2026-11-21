"""Phase 8.4: explanation quality, checked against references independent of our own code where possible.

For each benchmark position the app's rule-based explanation of its recommended move is produced and scored:
  - grounding: share of sentences that pass the grounding validator (factual support in engine facts)
  - move consistency: the summary names the recommended move, and that move is legal per python-chess
  - checkmate claims: "is checkmate" verified with python-chess; "forced mate in N" verified with Stockfish
  - material / tactical claims (fork, skewer, discovered/double attack, "wins about X pawns"): confirmed when
    Stockfish's own principal variation after the move (first 8 plies, replayed on a python-chess board) also gains
    >= 100 cp of material for the mover
  - stated evaluation vs Stockfish: sign agreement and absolute difference (clipped)
  - readability (descriptive only): sentences per explanation, words per sentence, Flesch reading ease
Human-judged criteria (strategic relevance, readability) still need human raters; see the report.

Usage (repo root): backend/.venv/bin/python research/benchmarks/explanation_eval.py [depth] [workers]
Writes research/reports/explanation_eval.{json,md}.
"""
import json
import re
import shutil
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import chess
import chess.engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.chess_core import Position
from app.explanation import explain_move
from app.intelligence import analyze
from app.search import SearchConfig

SF_DEPTH, CLIP = 16, 1000
MATERIAL_MOTIFS = {"fork", "skewer", "discovered_attack", "double_attack", "material_gain"}


@contextmanager
def stockfish():
    """One Stockfish per task (a long-lived engine thread would stop the pool worker from exiting)."""
    sf = chess.engine.SimpleEngine.popen_uci(shutil.which("stockfish"))
    try:
        sf.configure({"Threads": 1, "Hash": 64})
        yield sf
    finally:
        sf.quit()


MATERIAL = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900}


def material(board: chess.Board, color: chess.Color) -> int:
    return sum(v * (len(board.pieces(t, color)) - len(board.pieces(t, not color))) for t, v in MATERIAL.items())


def material_gain_along(board: chess.Board, pv: list, plies: int = 8) -> int:
    """Material change for the mover after playing Stockfish's principal variation (python-chess board)."""
    b, mover = board.copy(), board.turn
    start = material(b, mover)
    for m in pv[:plies]:
        if b.is_game_over():
            break
        b.push(m)
    return material(b, mover) - start


def syllables(word: str) -> int:
    groups = re.findall(r"[aeiouy]+", word.lower())
    return max(1, len(groups) - (word.lower().endswith("e") and len(groups) > 1))


def evaluate(args) -> dict:
    p, depth = args
    pos = Position(p["fen"])
    a = analyze(pos, SearchConfig(depth=depth, candidates=3, time_limit=10))
    if not a["candidates"]:
        return {"id": p["id"], "skipped": True}
    e = explain_move(pos, a)
    board = chess.Board(p["fen"])
    move = chess.Move.from_uci(e["move"])
    sentences = [e["summary"], *e["details"], *e["tactical_warnings"], *e["strategic_summary"],
                 *e["candidate_comparison"]]
    facts = {f["id"]: f for f in e["facts"]}
    with stockfish() as engine:
        best = engine.analyse(board, chess.engine.Limit(depth=SF_DEPTH))["score"].pov(board.turn)
        mine_info = engine.analyse(board, chess.engine.Limit(depth=SF_DEPTH), root_moves=[move])
    mine = mine_info["score"].pov(board.turn)
    sf_gain = material_gain_along(board, mine_info.get("pv", [move]))
    sf_move_cp, sf_best_cp = mine.score(mate_score=100_000), best.score(mate_score=100_000)
    loss = max(0, min(CLIP, sf_best_cp) - min(CLIP, sf_move_cp))

    claims = {"checkmate": [], "mate_in": [], "material": []}
    for s in e["details"]:
        motifs = {facts[i].get("motif") for i in s["facts"] if i in facts}
        if "checkmate" in motifs:
            b = board.copy()
            b.push(move)
            claims["checkmate"].append(b.is_checkmate())
        if motifs & MATERIAL_MOTIFS and "wins about" in s["text"]:
            claims["material"].append(sf_gain >= 100)  # Stockfish's own best line also wins >= a pawn
    ev = facts["eval"]
    if ev["mate_in"] and ev["mate_in"] > 0:
        claims["mate_in"].append(mine.is_mate() and 0 < mine.mate() <= ev["mate_in"])

    words = [w for s in sentences for w in re.findall(r"[A-Za-z]+", s["text"])]
    n_words = max(1, len(words))
    flesch = 206.835 - 1.015 * (n_words / len(sentences)) - 84.6 * (sum(map(syllables, words)) / n_words)
    our_cp = ev["score_cp"]
    return {
        "id": p["id"], "category": p["category"], "move": e["san"], "skipped": False,
        "sentences": len(sentences), "grounded": len(sentences) - len(e["grounding"]["rejected"]),
        "summary_names_move": e["san"].rstrip("+#") in e["summary"]["text"], "legal": move in board.legal_moves,
        "claims": claims, "sf_move_cp": sf_move_cp, "cp_loss": loss, "sf_line_material_gain": sf_gain,
        "eval_sign_agree": None if our_cp is None or abs(sf_move_cp) < 50 else (our_cp > 0) == (sf_move_cp > 0),
        "eval_abs_diff": None if our_cp is None else abs(max(-CLIP, min(CLIP, our_cp)) - max(-CLIP, min(CLIP, sf_move_cp))),
        "words_per_sentence": n_words / len(sentences), "flesch": flesch,
        "summary": e["summary"]["text"],
    }


def rate(values: list[bool]) -> str:
    return f"{sum(values)}/{len(values)} ({sum(values) / len(values):.0%})" if values else "– (none made)"


def main(depth: int, workers: int) -> None:
    data = json.loads((ROOT / "research" / "datasets" / "benchmark_positions.json").read_text())
    with ProcessPoolExecutor(max_workers=workers) as ex:
        rows = [r for r in ex.map(evaluate, [(p, depth) for p in data["positions"]]) if not r["skipped"]]
    allc = {k: [v for r in rows for v in r["claims"][k]] for k in ("checkmate", "mate_in", "material")}
    signs = [r["eval_sign_agree"] for r in rows if r["eval_sign_agree"] is not None]
    diffs = [r["eval_abs_diff"] for r in rows if r["eval_abs_diff"] is not None]
    sent = sum(r["sentences"] for r in rows)
    summary = {
        "explanations": len(rows), "sentences": sent, "grounded_share": sum(r["grounded"] for r in rows) / sent,
        "summary_names_move": sum(r["summary_names_move"] for r in rows) / len(rows),
        "legal_moves": sum(r["legal"] for r in rows) / len(rows),
        "checkmate_claims_true": allc["checkmate"], "mate_in_claims_true": allc["mate_in"],
        "material_claims_confirmed": allc["material"],
        "eval_sign_agreement": sum(signs) / len(signs) if signs else None,
        "eval_median_abs_diff": statistics.median(diffs) if diffs else None,
        "sentences_per_explanation": sent / len(rows),
        "words_per_sentence": statistics.mean(r["words_per_sentence"] for r in rows),
        "flesch": statistics.mean(r["flesch"] for r in rows),
    }
    reports = ROOT / "research" / "reports"
    (reports / "explanation_eval.json").write_text(json.dumps({"depth": depth, "summary": summary, "rows": rows},
                                                              indent=1))
    unconfirmed = [r for r in rows if False in r["claims"]["material"]]
    md = ["# Phase 8: explanation quality evaluation", "",
          (f"Rule-based explanations of the engine's recommended move for {len(rows)} benchmark positions "
           f"(analysis depth {depth}). Independent checks: python-chess for legality and checkmate, "
           f"Stockfish depth {SF_DEPTH} for mates, material/tactical claims and evaluations."), "",
          "| Criterion (roadmap 8.4) | Measure | Result |", "|---|---|---|",
          f"| Factual correctness | sentences passing grounding validation | {summary['grounded_share']:.0%} of {sent} |",
          f"| Factual correctness | \"is checkmate\" claims true (python-chess) | {rate(allc['checkmate'])} |",
          f"| Factual correctness | \"forced mate in N\" confirmed by Stockfish | {rate(allc['mate_in'])} |",
          f"| Move consistency | summary names the recommended move | {summary['summary_names_move']:.0%} |",
          f"| Move consistency | recommended move legal (python-chess) | {summary['legal_moves']:.0%} |",
          f"| Tactical accuracy | \"wins about X pawns\" claims: Stockfish's line also wins ≥ 1 pawn | {rate(allc['material'])} |",
          (f"| Tactical accuracy | stated evaluation has Stockfish's sign (when \\|SF\\| ≥ 50) | "
           f"{summary['eval_sign_agreement']:.0%} |"),
          f"| Tactical accuracy | median \\|our eval − Stockfish eval\\| (cp, clipped ±{CLIP}) | {summary['eval_median_abs_diff']:.0f} |",
          (f"| Readability (descriptive) | sentences per explanation / words per sentence / Flesch | "
           f"{summary['sentences_per_explanation']:.1f} / {summary['words_per_sentence']:.1f} / {summary['flesch']:.0f} |"),
          "| Strategic relevance, human readability | — | needs human raters (not measured) |", ""]
    md += ["## Material claims Stockfish did not confirm", ""]
    md += [f"- `{r['id']}` {r['move']}: Stockfish line material {r['sf_line_material_gain']:+d}, eval {r['sf_move_cp']:+d} cp, "
           f"loss {r['cp_loss']} cp — "
           f"\"{r['summary']}\"" for r in unconfirmed] or ["None."]
    md += ["", ("Grounding checks that each sentence matches the engine's own facts; the Stockfish checks measure "
                "whether those facts are right. " + (
                    "Since every sentence passed grounding, any unconfirmed claim traces back to the engine's facts "
                    f"(depth {depth} search), not to the explanation layer." if summary["grounded_share"] == 1
                    else "Some sentences failed grounding; see the JSON for which.")), ""]
    (reports / "explanation_eval.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4, int(sys.argv[2]) if len(sys.argv) > 2 else 4)
