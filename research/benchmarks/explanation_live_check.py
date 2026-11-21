"""Phase 6 live check: ask Claude to explain N positions and measure how its output fares under grounding.

Calls the real API (costs money; roughly one request per position). Needs ANTHROPIC_API_KEY or an `ant auth login`
profile. Usage (repo root): backend/.venv/bin/python research/benchmarks/explanation_live_check.py [n] [language]
Writes research/reports/explanation_live_check.{json,md}.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.chess_core import Position
from app.explanation import explain_move
from app.intelligence import analyze
from app.intelligence.benchmark import load
from app.search import SearchConfig


def main(n: int, language: str) -> None:
    fens = list(dict.fromkeys(c["fen"] for c in load()["cases"]))[:n]
    rows = []
    for fen in fens:
        pos = Position(fen)
        if not pos.legal_moves():
            continue
        a = analyze(pos, SearchConfig(depth=3, candidates=3))
        e = explain_move(pos, a, use_llm=True, language=language)
        g = e["grounding"]
        rows.append({"fen": fen, "move": e["san"], "source": e["source"], "checked": g["checked"],
                     "rejected": g["rejected"] + g.get("llm_rejected", []), "fallback_reason": g["fallback_reason"],
                     "summary": e["summary"]["text"], "tokens": e.get("llm")})
        print(f"{e['san']:8} {e['source']:10} rejected={len(rows[-1]['rejected'])} {g['fallback_reason'] or ''}")
    used = [r for r in rows if r["source"] == "llm"]
    sentences = sum(r["checked"] for r in used)
    rejected = sum(len(r["rejected"]) for r in used)
    reports = ROOT / "research" / "reports"
    (reports / "explanation_live_check.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    md = ["# Phase 6 live LLM grounding check", "",
          (f"{len(rows)} positions, language {language}. LLM explanation used for {len(used)}; "
          f"fell back to rule-based for {len(rows) - len(used)}."),
          (f"Of {sentences} LLM sentences that reached the user path, {rejected} were rejected by grounding "
          f"({rejected / max(sentences, 1):.0%})."), "", "## Rejected sentences", ""]
    md += [f"- {r['move']}: \"{x['text']}\" — {'; '.join(x['issues'])}" for r in rows for x in r["rejected"]] or ["None."]
    md += ["", "## Fallbacks", ""]
    md += [f"- {r['move']}: {r['fallback_reason']}" for r in rows if r["fallback_reason"]] or ["None."]
    (reports / "explanation_live_check.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10, sys.argv[2] if len(sys.argv) > 2 else "English")
