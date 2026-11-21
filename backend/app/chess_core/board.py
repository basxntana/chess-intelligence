"""0x88 board representation, FEN, legal move generation, make/unmake, draw rules.

Square index = rank * 16 + file (a1 = 0, h8 = 119). `sq & 0x88 != 0` means off-board.
Pieces are FEN letters: uppercase = white, lowercase = black, None = empty.
"""
from __future__ import annotations

import random
from typing import NamedTuple

WHITE, BLACK = "w", "b"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

KNIGHT_OFFSETS = (33, 31, 18, 14, -33, -31, -18, -14)
BISHOP_DIRS = (15, 17, -15, -17)
ROOK_DIRS = (1, -1, 16, -16)
KING_DIRS = BISHOP_DIRS + ROOK_DIRS
# Castling-right letter lost when a piece leaves/lands on that square.
CASTLE_SQUARES = {0: "Q", 7: "K", 4: "KQ", 112: "q", 119: "k", 116: "kq"}

WHITE_SET, BLACK_SET = frozenset("PNBRQK"), frozenset("pnbrqk")
SQUARES64 = [s for s in range(128) if not s & 0x88]


def _steps(offsets) -> list[list[int]]:
    return [[s + d for d in offsets if not (s + d) & 0x88] if not s & 0x88 else [] for s in range(128)]


def _rays(dirs) -> list[list[list[int]]]:
    out = []
    for s in range(128):
        rays = []
        for d in dirs:
            ray, t = [], s + d
            while not s & 0x88 and not t & 0x88:
                ray.append(t)
                t += d
            if ray:
                rays.append(ray)
        out.append(rays)
    return out


# Target squares per origin square, computed once so hot loops need no off-board checks.
# Direction order matches the *_DIRS tuples, keeping move generation order (and search tie-breaks) unchanged.
STEPS = {"n": _steps(KNIGHT_OFFSETS), "k": _steps(KING_DIRS)}
RAYS = {"b": _rays(BISHOP_DIRS), "r": _rays(ROOK_DIRS), "q": _rays(KING_DIRS)}
PAWN_ATTACKS = (_steps((15, 17)), _steps((-15, -17)))  # squares attacked by a white / black pawn

# Zobrist keys. Fixed seed so hashes (and therefore searches) are reproducible across runs.
_rng = random.Random(0x5EED)
Z_PIECE = {p: [_rng.getrandbits(64) for _ in range(128)] for p in "PNBRQKpnbrqk"}
Z_CASTLE = {c: _rng.getrandbits(64) for c in "KQkq"}
Z_EP = [_rng.getrandbits(64) for _ in range(8)]
Z_TURN = _rng.getrandbits(64)


def sq_name(sq: int) -> str:
    return "abcdefgh"[sq & 7] + str((sq >> 4) + 1)


def parse_sq(name: str) -> int:
    f, r = "abcdefgh".find(name[0]), int(name[1]) - 1
    if f < 0 or not 0 <= r < 8 or len(name) != 2:
        raise ValueError(f"bad square: {name}")
    return r * 16 + f


def color_of(piece: str) -> str:
    return WHITE if piece.isupper() else BLACK


class Move(NamedTuple):
    frm: int
    to: int
    promo: str | None = None  # lowercase piece letter

    @property
    def uci(self) -> str:
        return sq_name(self.frm) + sq_name(self.to) + (self.promo or "")

    def __str__(self) -> str:
        return self.uci


class FenError(ValueError):
    """FEN is syntactically malformed."""


class Position:
    def __init__(self, fen: str = START_FEN):
        self.board: list[str | None] = [None] * 128
        self._undo: list[tuple] = []
        self._keys: list[str] = []
        self.set_fen(fen)

    # ---------- FEN ----------
    def set_fen(self, fen: str) -> None:
        parts = fen.split()
        if len(parts) == 4:
            parts += ["0", "1"]
        if len(parts) != 6:
            raise FenError("FEN must have 4 or 6 fields")
        placement, turn, castling, ep, half, full = parts
        rows = placement.split("/")
        if len(rows) != 8:
            raise FenError("placement must have 8 ranks")
        board: list[str | None] = [None] * 128
        for i, row in enumerate(rows):
            rank, f = 7 - i, 0
            for ch in row:
                if ch.isdigit():
                    f += int(ch)
                elif ch in "pnbrqkPNBRQK":
                    if f > 7:
                        raise FenError(f"rank {rank + 1} overflows")
                    board[rank * 16 + f] = ch
                    f += 1
                else:
                    raise FenError(f"bad piece letter: {ch}")
            if f != 8:
                raise FenError(f"rank {rank + 1} does not have 8 files")
        if turn not in (WHITE, BLACK):
            raise FenError("active color must be w or b")
        if castling != "-" and (not set(castling) <= set("KQkq") or len(set(castling)) != len(castling)):
            raise FenError("bad castling field")
        try:
            ep_sq = None if ep == "-" else parse_sq(ep)
            half_i, full_i = int(half), int(full)
        except ValueError as e:
            raise FenError(str(e)) from None
        if half_i < 0 or full_i < 1:
            raise FenError("bad move counters")
        self.board, self.turn = board, turn
        self.castling = "".join(c for c in "KQkq" if c in castling)
        self.ep, self.halfmove, self.fullmove = ep_sq, half_i, full_i
        # Tracked incrementally in make/unmake; first king found if the FEN has several (validator rejects that).
        self.kings = {c: next((s for s in range(128) if board[s] == k), None) for c, k in ((WHITE, "K"), (BLACK, "k"))}
        self.hash = self.full_hash()
        self._undo, self._keys = [], [self.hash]

    def fen(self) -> str:
        rows = []
        for rank in range(7, -1, -1):
            row, empty = "", 0
            for f in range(8):
                p = self.board[rank * 16 + f]
                if p is None:
                    empty += 1
                else:
                    row += (str(empty) if empty else "") + p
                    empty = 0
            rows.append(row + (str(empty) if empty else ""))
        ep = sq_name(self.ep) if self.ep is not None else "-"
        return f"{'/'.join(rows)} {self.turn} {self.castling or '-'} {ep} {self.halfmove} {self.fullmove}"

    def full_hash(self) -> int:
        """Zobrist hash from scratch; make/unmake maintain `self.hash` incrementally."""
        h = Z_TURN if self.turn == BLACK else 0
        for s, p in enumerate(self.board):
            if p:
                h ^= Z_PIECE[p][s]
        for c in self.castling:
            h ^= Z_CASTLE[c]
        return h ^ self._ep_hash()

    def _ep_hash(self) -> int:
        # ep counts only if a capture is actually possible, so repetitions are detected correctly.
        return Z_EP[self.ep & 7] if self.ep is not None and self._ep_capturable() else 0

    def _ep_capturable(self) -> bool:
        pawn, d = ("P", -16) if self.turn == WHITE else ("p", 16)
        return any(not (s & 0x88) and self.board[s] == pawn for s in (self.ep + d - 1, self.ep + d + 1))

    # ---------- attacks ----------
    def king_sq(self, color: str) -> int | None:
        return self.kings[color]

    def is_attacked(self, sq: int, by: str) -> bool:
        b, white = self.board, by == WHITE
        pawn, knight, king = ("P", "N", "K") if white else ("p", "n", "k")
        diag, ortho = ("B", "Q") if white else ("b", "q"), ("R", "Q") if white else ("r", "q")
        for d in ((-15, -17) if white else (15, 17)):  # pawns attack from behind the target
            s = sq + d
            if not s & 0x88 and b[s] == pawn:
                return True
        for d in KNIGHT_OFFSETS:
            s = sq + d
            if not s & 0x88 and b[s] == knight:
                return True
        for d in KING_DIRS:
            s = sq + d
            if not s & 0x88 and b[s] == king:
                return True
        for dirs, sliders in ((BISHOP_DIRS, diag), (ROOK_DIRS, ortho)):
            for d in dirs:
                s = sq + d
                while not s & 0x88:
                    if b[s] is not None:
                        if b[s] in sliders:
                            return True
                        break
                    s += d
        return False

    def in_check(self, color: str | None = None) -> bool:
        color = color or self.turn
        k = self.king_sq(color)
        return k is not None and self.is_attacked(k, BLACK if color == WHITE else WHITE)

    # ---------- move generation ----------
    def pseudo_moves(self) -> list[Move]:
        b, us = self.board, self.turn
        them = BLACK if us == WHITE else WHITE
        own, enemy = (WHITE_SET, BLACK_SET) if us == WHITE else (BLACK_SET, WHITE_SET)
        moves: list[Move] = []
        append = moves.append
        for frm in SQUARES64:
            p = b[frm]
            if p is None or p not in own:
                continue
            kind = p.lower()
            if kind == "p":
                fwd, start_rank, promo_rank = (16, 1, 7) if us == WHITE else (-16, 6, 0)
                to = frm + fwd
                if not to & 0x88 and b[to] is None:
                    self._add_pawn(moves, frm, to, promo_rank)
                    if frm >> 4 == start_rank and b[to + fwd] is None:
                        append(Move(frm, to + fwd))
                for to in (frm + fwd - 1, frm + fwd + 1):
                    if to & 0x88:
                        continue
                    if b[to] in enemy or to == self.ep:
                        self._add_pawn(moves, frm, to, promo_rank)
            elif kind in STEPS:
                for to in STEPS[kind][frm]:
                    q = b[to]
                    if q is None or q in enemy:
                        append(Move(frm, to))
            else:
                for ray in RAYS[kind][frm]:
                    for to in ray:
                        q = b[to]
                        if q is None:
                            append(Move(frm, to))
                        else:
                            if q in enemy:
                                append(Move(frm, to))
                            break
        self._add_castling(moves, us, them)
        return moves

    @staticmethod
    def _add_pawn(moves: list[Move], frm: int, to: int, promo_rank: int) -> None:
        if to >> 4 == promo_rank:
            moves.extend(Move(frm, to, p) for p in "qrbn")
        else:
            moves.append(Move(frm, to))

    def _add_castling(self, moves: list[Move], us: str, them: str) -> None:
        b = self.board
        base, king, rook = (0, "K", "R") if us == WHITE else (112, "k", "r")
        rights = self.castling if us == WHITE else self.castling.swapcase()
        if b[base + 4] != king or ("K" not in rights and "Q" not in rights):
            return
        if self.is_attacked(base + 4, them):
            return
        if ("K" in rights and b[base + 7] == rook and b[base + 5] is None and b[base + 6] is None
                and not self.is_attacked(base + 5, them) and not self.is_attacked(base + 6, them)):
            moves.append(Move(base + 4, base + 6))
        if ("Q" in rights and b[base] == rook and b[base + 1] is None and b[base + 2] is None
                and b[base + 3] is None and not self.is_attacked(base + 3, them)
                and not self.is_attacked(base + 2, them)):
            moves.append(Move(base + 4, base + 2))

    def legal_moves(self) -> list[Move]:
        us, legal = self.turn, []
        for m in self.pseudo_moves():
            self.make(m)
            if not self.in_check(us):
                legal.append(m)
            self.unmake()
        return legal

    def parse_uci(self, uci: str) -> Move:
        """Return the legal move matching a UCI string, or raise ValueError."""
        for m in self.legal_moves():
            if m.uci == uci:
                return m
        raise ValueError(f"illegal move: {uci}")

    # ---------- make / unmake ----------
    def make(self, m: Move) -> None:
        b, us = self.board, self.turn
        piece, captured, cap_sq = b[m.frm], b[m.to], None
        old_castling = self.castling
        self._undo.append((m, captured, old_castling, self.ep, self.halfmove, self.fullmove, None, self.hash))
        h = self.hash ^ self._ep_hash() ^ Z_TURN
        is_pawn = piece in "Pp"
        if is_pawn and m.to == self.ep and captured is None:  # en passant
            cap_sq = m.to - 16 if piece == "P" else m.to + 16
            captured = b[cap_sq]
            b[cap_sq] = None
            h ^= Z_PIECE[captured][cap_sq]
            self._undo[-1] = (m, captured, old_castling, self.ep, self.halfmove, self.fullmove, cap_sq, self.hash)
        elif captured:
            h ^= Z_PIECE[captured][m.to]
        placed = (m.promo.upper() if us == WHITE else m.promo) if m.promo else piece
        b[m.to], b[m.frm] = placed, None
        h ^= Z_PIECE[piece][m.frm] ^ Z_PIECE[placed][m.to]
        if piece in "Kk":
            self.kings[us] = m.to
            if abs(m.to - m.frm) == 2:  # castling: move the rook too
                rook_from, rook_to = (m.frm + 3, m.frm + 1) if m.to > m.frm else (m.frm - 4, m.frm - 1)
                rook = b[rook_from]
                b[rook_to], b[rook_from] = rook, None
                h ^= Z_PIECE[rook][rook_from] ^ Z_PIECE[rook][rook_to]
        for s in (m.frm, m.to):
            if s in CASTLE_SQUARES:
                self.castling = "".join(c for c in self.castling if c not in CASTLE_SQUARES[s])
        for c in old_castling:
            if c not in self.castling:
                h ^= Z_CASTLE[c]
        self.ep = (m.frm + m.to) // 2 if is_pawn and abs(m.to - m.frm) == 32 else None
        self.halfmove = 0 if is_pawn or captured else self.halfmove + 1
        if us == BLACK:
            self.fullmove += 1
        self.turn = BLACK if us == WHITE else WHITE
        self.hash = h ^ self._ep_hash()
        self._keys.append(self.hash)

    def unmake(self) -> None:
        m, captured, self.castling, self.ep, self.halfmove, self.fullmove, cap_sq, self.hash = self._undo.pop()
        self._keys.pop()
        self.turn = us = BLACK if self.turn == WHITE else WHITE
        b = self.board
        piece = ("P" if us == WHITE else "p") if m.promo else b[m.to]
        b[m.frm], b[m.to] = piece, None
        if cap_sq is not None:  # en passant
            b[cap_sq] = captured
        else:
            b[m.to] = captured
        if piece in "Kk":
            self.kings[us] = m.frm
            if abs(m.to - m.frm) == 2:
                rook_from, rook_to = (m.frm + 3, m.frm + 1) if m.to > m.frm else (m.frm - 4, m.frm - 1)
                b[rook_from], b[rook_to] = b[rook_to], None

    # ---------- game state ----------
    def is_checkmate(self) -> bool:
        return self.in_check() and not self.legal_moves()

    def is_stalemate(self) -> bool:
        return not self.in_check() and not self.legal_moves()

    def is_insufficient_material(self) -> bool:
        pieces = [(p, s) for s, p in enumerate(self.board) if not s & 0x88 and p and p not in "Kk"]
        if not pieces:
            return True
        if any(p in "PpRrQq" for p, _ in pieces):
            return False
        if len(pieces) == 1:  # K+minor vs K
            return True
        # Only bishops, all on same square color -> no mate possible.
        return all(p in "Bb" for p, _ in pieces) and len({((s >> 4) + (s & 7)) % 2 for _, s in pieces}) == 1

    def is_fifty_move(self) -> bool:
        return self.halfmove >= 100

    def is_threefold(self) -> bool:
        return self._keys.count(self._keys[-1]) >= 3

    def status(self) -> str:
        if not self.legal_moves():
            return "checkmate" if self.in_check() else "stalemate"
        if self.is_insufficient_material():
            return "insufficient_material"
        if self.is_fifty_move():
            return "fifty_move"
        if self.is_threefold():
            return "threefold_repetition"
        return "ongoing"


def perft(pos: Position, depth: int) -> int:
    if depth == 0:
        return 1
    moves = pos.legal_moves()
    if depth == 1:
        return len(moves)
    n = 0
    for m in moves:
        pos.make(m)
        n += perft(pos, depth - 1)
        pos.unmake()
    return n
