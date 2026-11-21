"""Attack primitives on a raw 0x88 board list: attackers, attacked squares, static exchange evaluation."""
from __future__ import annotations

from .board import BISHOP_DIRS, KING_DIRS, KNIGHT_OFFSETS, ROOK_DIRS, Position

VALUE = {"p": 100, "n": 320, "b": 330, "r": 500, "q": 900, "k": 20_000}  # king: "infinite" for exchanges
SLIDER_DIRS = {"b": BISHOP_DIRS, "r": ROOK_DIRS, "q": KING_DIRS}
SQUARES = [r * 16 + f for r in range(8) for f in range(8)]


def value(piece: str) -> int:
    return VALUE[piece.lower()]


def attacks_from(b: list, sq: int) -> list[int]:
    """Squares the piece on `sq` attacks (own-occupied included: that is a defence)."""
    p = b[sq]
    k = p.lower()
    if k == "p":
        steps = (15, 17) if p.isupper() else (-15, -17)
        return [sq + d for d in steps if not (sq + d) & 0x88]
    if k in "nk":
        return [sq + d for d in (KNIGHT_OFFSETS if k == "n" else KING_DIRS) if not (sq + d) & 0x88]
    out = []
    for d in SLIDER_DIRS[k]:
        t = sq + d
        while not t & 0x88:
            out.append(t)
            if b[t]:
                break
            t += d
    return out


def attackers(b: list, sq: int, white: bool) -> list[int]:
    """Squares of `white`'s pieces that attack `sq` (pins ignored, as in standard SEE)."""
    out = []
    pawn, knight, king = ("P", "N", "K") if white else ("p", "n", "k")
    for d in ((-15, -17) if white else (15, 17)):
        if not (sq + d) & 0x88 and b[sq + d] == pawn:
            out.append(sq + d)
    for d in KNIGHT_OFFSETS:
        if not (sq + d) & 0x88 and b[sq + d] == knight:
            out.append(sq + d)
    for d in KING_DIRS:
        if not (sq + d) & 0x88 and b[sq + d] == king:
            out.append(sq + d)
    for dirs, kinds in ((BISHOP_DIRS, "bq"), (ROOK_DIRS, "rq")):
        for d in dirs:
            t = sq + d
            while not t & 0x88:
                p = b[t]
                if p:
                    if p.isupper() == white and p.lower() in kinds:
                        out.append(t)
                    break
                t += d
    return out


def see(b: list, frm: int, to: int) -> int:
    """Material the side moving frm->to expects from the capture sequence on `to` (swap algorithm).
    Each side may stop capturing; x-rays appear because captured pieces are removed from a board copy."""
    b = b[:]
    target = b[to]
    gains = [value(target) if target else 0]
    on_square = value(b[frm])
    white = not b[frm].isupper()  # side to recapture
    b[to], b[frm] = b[frm], None
    while atk := attackers(b, to, white):
        a = min(atk, key=lambda s: value(b[s]))
        gains.append(on_square - gains[-1])
        on_square = value(b[a])
        b[to], b[a] = b[a], None
        white = not white
    for i in range(len(gains) - 1, 0, -1):
        gains[i - 1] = -max(-gains[i - 1], gains[i])
    return gains[0]


def with_turn(pos: Position, color: str) -> Position:
    """The same board with `color` to move ("null move"), en passant cleared. Used to ask what a side threatens."""
    if pos.turn == color:
        return pos
    placement, _, castling, _, half, full = pos.fen().split()
    return Position(f"{placement} {color} {castling} - {half} {full}")
