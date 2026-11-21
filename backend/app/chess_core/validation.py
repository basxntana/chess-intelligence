"""FR-02: distinguish syntactically valid FEN from a legal chess state."""
from __future__ import annotations

from .board import BLACK, WHITE, FenError, Position, sq_name


def validate_fen(fen: str) -> dict:
    """Return {'syntax_valid', 'legal', 'errors', 'fen', 'status', 'in_check', 'legal_moves'}."""
    try:
        pos = Position(fen)
    except FenError as e:
        return {"syntax_valid": False, "legal": False, "errors": [str(e)]}
    errors = position_errors(pos)
    result = {"syntax_valid": True, "legal": not errors, "errors": errors, "fen": pos.fen()}
    if not errors:
        moves = pos.legal_moves()
        result.update(status=pos.status(), in_check=pos.in_check(), legal_moves=[m.uci for m in moves])
    return result


def position_errors(pos: Position) -> list[str]:
    b, errors = pos.board, []
    squares = [(s, p) for s, p in enumerate(b) if not s & 0x88 and p]
    for color, king in ((WHITE, "K"), (BLACK, "k")):
        n = sum(p == king for _, p in squares)
        if n != 1:
            errors.append(f"{'white' if color == WHITE else 'black'} must have exactly one king (found {n})")
    for s, p in squares:
        if p in "Pp" and s >> 4 in (0, 7):
            errors.append(f"pawn on back rank: {sq_name(s)}")
    for color, pawn, minors in ((WHITE, "P", "NBRQ"), (BLACK, "p", "nbrq")):
        pawns = sum(p == pawn for _, p in squares)
        # Extra pieces beyond the starting set must come from promoted pawns.
        start = {"N": 2, "B": 2, "R": 2, "Q": 1}
        promoted = sum(max(0, sum(p == m for _, p in squares) - start[m.upper()]) for m in minors)
        if pawns > 8 or pawns + promoted > 8:
            errors.append(f"{'white' if color == WHITE else 'black'} has too many pawns/promoted pieces")
    if errors:  # king-dependent checks below need exactly one king each
        return errors
    if pos.in_check(BLACK if pos.turn == WHITE else WHITE):
        errors.append("side not to move is in check")
    for right, king_sq, king, rook_sq, rook in (("K", 4, "K", 7, "R"), ("Q", 4, "K", 0, "R"),
                                                ("k", 116, "k", 119, "r"), ("q", 116, "k", 112, "r")):
        if right in pos.castling and (b[king_sq] != king or b[rook_sq] != rook):
            errors.append(f"castling right {right} without king and rook on original squares")
    if pos.ep is not None:
        # ep square must be on rank 6 (white to move) / rank 3 (black), behind a just-pushed enemy pawn.
        rank, pawn_sq, pawn, origin = (5, pos.ep - 16, "p", pos.ep + 16) if pos.turn == WHITE \
            else (2, pos.ep + 16, "P", pos.ep - 16)
        if pos.ep >> 4 != rank or b[pawn_sq] != pawn or b[pos.ep] or b[origin]:
            errors.append(f"inconsistent en passant square {sq_name(pos.ep)}")
    return errors
