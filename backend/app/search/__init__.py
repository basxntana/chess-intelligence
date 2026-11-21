"""Phase 3 custom search: minimax, negamax, alpha-beta + ordering, iterative deepening, quiescence, TT.

Each technique is a SearchConfig flag so experiments E1-E7 differ only by configuration.
Scores are centipawns from the side to move's perspective unless named *_white.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Literal

from app.chess_core import Move, Position
from app.chess_core.attacks import see
from app.chess_core.board import WHITE
from app.evaluation import DEFAULT as DEFAULT_EVAL
from app.evaluation import PIECE_VALUES, EvalConfig, evaluate

MATE = 100_000
MATE_BOUND = MATE - 1_000  # |score| above this means forced mate
INF = MATE + 1
EXACT, LOWER, UPPER = 0, 1, 2
DELTA_MARGIN = 200  # quiescence: max positional swing assumed for a capture
TT_MAX_ENTRIES = 1_000_000  # shortcut: cleared when full instead of replacement scheme; fine for Python NPS.


@dataclass(frozen=True)
class SearchConfig:
    depth: int = 4
    time_limit: float | None = None  # seconds; at least one root move is always scored
    candidates: int = 1  # multi-PV: number of exact-scored root moves
    algorithm: Literal["minimax", "negamax", "alphabeta"] = "alphabeta"
    move_ordering: bool = True
    iterative_deepening: bool = True
    quiescence: bool = True
    transposition_table: bool = True
    eval: EvalConfig = DEFAULT_EVAL


@dataclass
class Candidate:
    move: str
    score: int
    pv: list[str]
    mate_in: int | None = None  # >0: side to move mates, <0: gets mated


@dataclass
class SearchResult:
    best_move: str | None
    score: int
    score_white: int
    mate_in: int | None
    pv: list[str]
    candidates: list[Candidate]
    depth: int
    nodes: int
    time: float
    nps: int
    terminal: str | None = None  # "checkmate"/"stalemate" when the root has no legal moves
    config: dict = field(default_factory=dict)


class SearchTimeout(Exception):
    pass


def mate_in(score: int) -> int | None:
    if abs(score) < MATE_BOUND:
        return None
    plies = MATE - abs(score)
    return (plies + 1) // 2 * (1 if score > 0 else -1)


def search(pos: Position, config: SearchConfig = SearchConfig(),
           on_iteration: Callable[[int, list[Candidate], int, float], None] | None = None) -> SearchResult:
    """`on_iteration(depth, candidates, nodes, seconds)` is called after each completed iterative-deepening depth,
    so callers can show a best-so-far result while the search continues."""
    return Searcher(pos, config, on_iteration).run()


class Searcher:
    def __init__(self, pos: Position, cfg: SearchConfig, on_iteration=None):
        self.pos, self.cfg = pos, cfg
        self.tt: dict[int, tuple[int, int, int, Move | None]] = {}
        self.killers: dict[int, list[Move]] = {}
        self.history: dict[tuple[int, int], int] = {}
        self.eval_cache: dict[int, int] = {}
        self.nodes = 0
        self.deadline: float | None = None
        self.can_abort = False
        self.on_iteration = on_iteration

    # ---------- driver ----------
    def run(self) -> SearchResult:
        cfg, pos = self.cfg, self.pos
        start = time.perf_counter()
        self.deadline = start + cfg.time_limit if cfg.time_limit else None
        root_moves = pos.legal_moves()
        if not root_moves:
            checkmated = pos.in_check()
            score = -MATE if checkmated else 0
            return self._result(None, score, [], 0, start, "checkmate" if checkmated else "stalemate")

        base = len(pos._undo)
        done: tuple[int, list[Candidate]] | None = None
        for depth in range(1, cfg.depth + 1) if cfg.iterative_deepening else [cfg.depth]:
            self.can_abort = done is not None
            self.partial: list = []
            try:
                cands = self._root(depth, root_moves)
            except SearchTimeout:
                while len(pos._undo) > base:  # unwind the aborted line
                    pos.unmake()
                if done is None:  # first iteration cut short: use the root moves that finished (>= 1)
                    done = (depth, self._candidates(self.partial, depth))
                break
            done = (depth, cands)
            if self.on_iteration:
                self.on_iteration(depth, cands, self.nodes, time.perf_counter() - start)
            if cfg.move_ordering:  # previous iteration's best moves first
                ranked = {c.move: i for i, c in enumerate(cands)}
                root_moves.sort(key=lambda m: ranked.get(m.uci, len(ranked)))
            if abs(cands[0].score) >= MATE_BOUND:  # shorter mates were excluded by shallower iterations
                break
            if self.deadline and time.perf_counter() > self.deadline:
                break
        depth, cands = done
        return self._result(cands[0].move, cands[0].score, cands, depth, start)

    def _result(self, best, score, cands, depth, start, terminal=None) -> SearchResult:
        elapsed = time.perf_counter() - start
        white = self.pos.turn == WHITE
        return SearchResult(
            best_move=best, score=score, score_white=score if white else -score, mate_in=mate_in(score),
            pv=cands[0].pv if cands else [], candidates=cands, depth=depth, nodes=self.nodes,
            time=round(elapsed, 4), nps=int(self.nodes / elapsed) if elapsed > 0 else 0,
            terminal=terminal, config=asdict(self.cfg),
        )

    def _root(self, depth: int, moves: list[Move]) -> list[Candidate]:
        k, pos = self.cfg.candidates, self.pos
        scored: list[tuple[int, Move, list[Move]]] = self.partial
        for m in moves:
            # A move must beat the current k-th best to be a candidate; others may fail low (score is a bound).
            alpha = sorted((s for s, _, _ in scored), reverse=True)[k - 1] if len(scored) >= k else -INF
            pos.make(m)
            if self.cfg.algorithm == "minimax":
                s, pv = self._minimax(depth - 1, 1)
                s = s if pos.turn != WHITE else -s  # white-perspective -> root mover's perspective
            elif self.cfg.algorithm == "negamax":
                s, pv = self._negamax(depth - 1, 1, -INF, INF, prune=False)
                s = -s
            else:
                s, pv = self._negamax(depth - 1, 1, -INF, -alpha, prune=True)
                s = -s
            pos.unmake()
            if s > alpha:
                scored.append((s, m, [m, *pv]))
            self.can_abort = self.deadline is not None  # at least one root move is scored now
        return self._candidates(scored, depth)

    def _candidates(self, scored: list, depth: int) -> list[Candidate]:
        k = self.cfg.candidates
        scored = sorted(scored, key=lambda t: -t[0])  # stable: ties keep move order -> deterministic
        return [Candidate(m.uci, s, [x.uci for x in self._extend_pv(pv, depth)], mate_in(s))
                for s, m, pv in scored[:k]]

    def _extend_pv(self, pv: list[Move], depth: int) -> list[Move]:
        """TT cutoffs truncate PVs; follow stored best moves (checked legal) to fill them back in."""
        pos, pv = self.pos, list(pv)
        for m in pv:
            pos.make(m)
        while len(pv) < depth and (e := self.tt.get(pos.hash)) and e[3] in pos.legal_moves():
            pv.append(e[3])
            pos.make(e[3])
        for _ in pv:
            pos.unmake()
        return pv

    # ---------- helpers ----------
    def _tick(self) -> None:
        self.nodes += 1
        if self.can_abort and self.deadline and not self.nodes & 1023 and time.perf_counter() > self.deadline:
            raise SearchTimeout

    def _is_draw(self) -> bool:
        pos = self.pos
        # shortcut: insufficient material is left to the evaluation (Phase 4) instead of scored as a draw here.
        return pos.halfmove >= 100 or pos.hash in pos._keys[-pos.halfmove - 1:-1]

    def _eval_white(self) -> int:
        # Board-only eval, so the Zobrist hash is a valid cache key.
        h = self.pos.hash
        e = self.eval_cache.get(h)
        if e is None:
            if len(self.eval_cache) >= TT_MAX_ENTRIES:
                self.eval_cache.clear()
            e = self.eval_cache[h] = evaluate(self.pos, self.cfg.eval)
        return e

    def _eval(self) -> int:
        e = self._eval_white()
        return e if self.pos.turn == WHITE else -e

    def _victim(self, m: Move) -> int:
        p = self.pos.board[m.to]
        if p:
            return PIECE_VALUES[p.lower()]
        return PIECE_VALUES["p"] if m.to == self.pos.ep and self.pos.board[m.frm] in "Pp" else 0

    def _losing_capture(self, m: Move, victim: int) -> bool:
        """Static exchange evaluation says the capture sequence loses material. Only a pricier attacker can lose."""
        b = self.pos.board
        return PIECE_VALUES[b[m.frm].lower()] > victim and see(b, m.frm, m.to) < 0

    def _order(self, moves: list[Move], ply: int, tt_move: Move | None) -> list[Move]:
        if not self.cfg.move_ordering:
            return moves
        b, killers = self.pos.board, self.killers.get(ply, ())

        def key(m: Move) -> int:
            if m == tt_move:
                return 10_000_000
            victim = self._victim(m)
            if victim:  # MVV-LVA
                return 1_000_000 + 10 * victim - PIECE_VALUES[b[m.frm].lower()]
            if m.promo:
                return 900_000 + PIECE_VALUES[m.promo]
            if m in killers:
                return 800_000
            return self.history.get((m.frm, m.to), 0)

        return sorted(moves, key=key, reverse=True)

    # ---------- E1: minimax (White maximizes, Black minimizes; scores from White's view) ----------
    def _minimax(self, depth: int, ply: int) -> tuple[int, list[Move]]:
        self._tick()
        pos = self.pos
        if self._is_draw():
            return 0, []
        if depth <= 0:
            return self._eval_white(), []
        us = pos.turn
        maximizing = us == WHITE
        best, best_pv, legal = (-INF if maximizing else INF), [], 0
        for m in pos.pseudo_moves():
            pos.make(m)
            if pos.in_check(us):
                pos.unmake()
                continue
            legal += 1
            s, pv = self._minimax(depth - 1, ply + 1)
            pos.unmake()
            if (s > best) if maximizing else (s < best):
                best, best_pv = s, [m, *pv]
        if not legal:
            if not pos.in_check():
                return 0, []
            return (-(MATE - ply) if maximizing else MATE - ply), []
        return best, best_pv

    # ---------- E2-E7: negamax, optionally with alpha-beta / TT / ordering ----------
    def _negamax(self, depth: int, ply: int, alpha: int, beta: int, prune: bool) -> tuple[int, list[Move]]:
        self._tick()
        pos = self.pos
        if self._is_draw():
            return 0, []
        if depth <= 0:
            return (self._qsearch(alpha, beta, ply) if self.cfg.quiescence else self._eval()), []

        use_tt = self.cfg.transposition_table
        tt_move, alpha_orig = None, alpha
        if use_tt and (e := self.tt.get(pos.hash)):
            e_depth, e_score, e_flag, tt_move = e
            if e_depth >= depth:
                s = e_score - ply if e_score > MATE_BOUND else e_score + ply if e_score < -MATE_BOUND else e_score
                if e_flag == EXACT or (e_flag == LOWER and s >= beta) or (e_flag == UPPER and s <= alpha):
                    return s, [tt_move] if tt_move else []

        us = pos.turn
        best, best_move, best_pv, legal = -INF, None, [], 0
        for m in self._order(pos.pseudo_moves(), ply, tt_move):
            pos.make(m)
            if pos.in_check(us):
                pos.unmake()
                continue
            legal += 1
            s, pv = self._negamax(depth - 1, ply + 1, -beta, -alpha, prune)
            s = -s
            pos.unmake()
            if s > best:
                best, best_move, best_pv = s, m, [m, *pv]
                alpha = max(alpha, s)
            if prune and alpha >= beta:
                if not self._victim(m) and not m.promo:  # quiet cutoff move: remember it
                    killers = self.killers.setdefault(ply, [])
                    if m not in killers:
                        killers[:] = [m, *killers][:2]
                    self.history[(m.frm, m.to)] = self.history.get((m.frm, m.to), 0) + depth * depth
                break
        if not legal:
            return (-(MATE - ply) if pos.in_check() else 0), []

        if use_tt:
            flag = UPPER if best <= alpha_orig else LOWER if best >= beta else EXACT
            stored = best + ply if best > MATE_BOUND else best - ply if best < -MATE_BOUND else best
            if len(self.tt) >= TT_MAX_ENTRIES:
                self.tt.clear()
            self.tt[pos.hash] = (depth, stored, flag, best_move)
        return best, best_pv

    # ---------- E6: quiescence (captures/promotions; all evasions when in check) ----------
    def _qsearch(self, alpha: int, beta: int, ply: int) -> int:
        self._tick()
        pos = self.pos
        in_check = pos.in_check()
        best = -INF
        if not in_check:
            best = self._eval()  # stand pat
            if best >= beta:
                return best
            alpha = max(alpha, best)
        moves = pos.pseudo_moves()
        if not in_check:
            # Delta pruning: skip captures that cannot lift the score to alpha even with a safety margin.
            moves = [m for m in moves if m.promo or (v := self._victim(m)) and best + v + DELTA_MARGIN > alpha
                     and not self._losing_capture(m, v)]
        us, legal = pos.turn, 0
        for m in self._order(moves, ply, None):
            pos.make(m)
            if pos.in_check(us):
                pos.unmake()
                continue
            legal += 1
            s = -self._qsearch(-beta, -alpha, ply + 1)
            pos.unmake()
            if s > best:
                best = s
                if s > alpha:
                    alpha = s
                    if alpha >= beta:
                        break
        if in_check and not legal:
            return -(MATE - ply)
        return best
