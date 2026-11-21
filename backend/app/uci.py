"""Minimal UCI front-end for the custom engine: `python -m app.uci`.

Supports uci / isready / ucinewgame / position [startpos|fen ...] [moves ...] / go [depth|movetime|wtime/btime/winc/binc]
/ quit, and the option `Depth` (max depth when no limit is given). Search is synchronous, so `stop` is not needed:
`go` always returns a bestmove within its time budget.
"""
from __future__ import annotations

import sys

from .chess_core import START_FEN, Position
from .config import settings
from .search import SearchConfig, search

MAX_DEPTH = 64


def time_budget(tokens: dict[str, float], white: bool) -> float | None:
    if "movetime" in tokens:
        return tokens["movetime"] / 1000
    left = tokens.get("wtime" if white else "btime")
    if left is None:
        return None
    inc = tokens.get("winc" if white else "binc", 0)
    # Spend ~1/30 of the clock plus most of the increment, never more than a third of what is left.
    return max(0.05, min(left / 30 + inc * 0.8, left / 3)) / 1000


def parse_position(args: list[str]) -> Position:
    if args[0] == "startpos":
        pos, rest = Position(START_FEN), args[1:]
    else:
        end = args.index("moves") if "moves" in args else len(args)
        pos, rest = Position(" ".join(args[1:end])), args[end:]
    if rest and rest[0] == "moves":
        for uci in rest[1:]:
            pos.make(pos.parse_uci(uci))
    return pos


def score_text(score: int, mate_in: int | None) -> str:
    return f"mate {mate_in}" if mate_in is not None else f"cp {score}"


def main(inp=sys.stdin, out=sys.stdout) -> None:
    def send(line: str) -> None:
        out.write(line + "\n")
        out.flush()

    pos, default_depth = Position(START_FEN), 8
    for raw in inp:
        parts = raw.split()
        if not parts:
            continue
        cmd, args = parts[0], parts[1:]
        if cmd == "uci":
            send(f"id name ChessIntelligence {settings.engine_version}")
            send("id author Chess Intelligence project")
            send(f"option name Depth type spin default {default_depth} min 1 max {MAX_DEPTH}")
            send("uciok")
        elif cmd == "isready":
            send("readyok")
        elif cmd == "setoption" and len(args) >= 4 and args[1].lower() == "depth":
            default_depth = max(1, min(MAX_DEPTH, int(args[3])))
        elif cmd == "ucinewgame":
            pos = Position(START_FEN)
        elif cmd == "position" and args:
            try:
                pos = parse_position(args)
            except ValueError as e:
                send(f"info string invalid position: {e}")
        elif cmd == "go":
            tokens = {args[i]: float(args[i + 1]) for i in range(len(args) - 1)
                      if args[i] in ("depth", "movetime", "wtime", "btime", "winc", "binc")}
            budget = time_budget(tokens, pos.turn == "w")
            depth = int(tokens["depth"]) if "depth" in tokens else (MAX_DEPTH if budget else default_depth)
            r = search(pos, SearchConfig(depth=depth, time_limit=budget))
            if r.best_move is None:
                send("bestmove 0000")
                continue
            send(f"info depth {r.depth} score {score_text(r.score, r.mate_in)} nodes {r.nodes} nps {r.nps} "
                 f"time {int(r.time * 1000)} pv {' '.join(r.pv)}")
            send(f"bestmove {r.best_move}")
        elif cmd == "quit":
            return


if __name__ == "__main__":
    main()
