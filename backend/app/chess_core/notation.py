"""Standard Algebraic Notation (SAN) for legal moves."""
from __future__ import annotations

from .board import Move, Position, sq_name


def san(pos: Position, m: Move) -> str:
    """SAN of a legal move in `pos` (e.g. Nbd2, exd5, e8=Q+, O-O, Qh5#)."""
    piece = pos.board[m.frm]
    kind = piece.lower()
    if kind == "k" and abs(m.to - m.frm) == 2:
        text = "O-O" if m.to > m.frm else "O-O-O"
    else:
        capture = pos.board[m.to] is not None or (kind == "p" and m.to == pos.ep)
        if kind == "p":
            text = (sq_name(m.frm)[0] + "x" if capture else "") + sq_name(m.to)
            if m.promo:
                text += "=" + m.promo.upper()
        else:
            rivals = [o.frm for o in pos.legal_moves() if o.to == m.to and o.frm != m.frm and pos.board[o.frm] == piece]
            disambig = ""
            if rivals:
                if all((r & 7) != (m.frm & 7) for r in rivals):
                    disambig = sq_name(m.frm)[0]
                elif all((r >> 4) != (m.frm >> 4) for r in rivals):
                    disambig = sq_name(m.frm)[1]
                else:
                    disambig = sq_name(m.frm)
            text = kind.upper() + disambig + ("x" if capture else "") + sq_name(m.to)
    pos.make(m)
    if pos.in_check():
        text += "#" if not pos.legal_moves() else "+"
    pos.unmake()
    return text


def line_san(pos: Position, ucis: list[str]) -> list[str]:
    """SAN for a sequence of UCI moves played from `pos` (position is restored)."""
    out = []
    for u in ucis:
        m = pos.parse_uci(u)
        out.append(san(pos, m))
        pos.make(m)
    for _ in out:
        pos.unmake()
    return out
