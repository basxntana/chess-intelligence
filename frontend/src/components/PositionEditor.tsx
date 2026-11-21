"use client";

import type { Piece, Role } from "chessground/types";
import { Button, PieceIcon } from "./ui";

export type EditState = { turn: "w" | "b"; castling: string; ep: string };

const ROLES: Role[] = ["king", "queen", "rook", "bishop", "knight", "pawn"];

type Props = {
  placing: Piece | "delete" | null;
  setPlacing: (p: Piece | "delete" | null) => void;
  state: EditState;
  setState: (s: EditState) => void;
  onClear: () => void;
  onStart: () => void;
};

/** Piece palette and side/castling/en-passant controls. The backend decides whether the result is legal. */
export default function PositionEditor({ placing, setPlacing, state, setState, onClear, onStart }: Props) {
  const isActive = (p: Piece | "delete") =>
    placing === p || (placing !== null && placing !== "delete" && p !== "delete" && placing.role === p.role && placing.color === p.color);
  const toggleCastle = (c: string) => {
    const next = state.castling.includes(c) ? state.castling.replace(c, "") : state.castling + c;
    setState({ ...state, castling: "KQkq".split("").filter((x) => next.includes(x)).join("") });
  };
  return (
    <div className="space-y-4 text-sm">
      <p className="text-xs text-muted">
        Drag pieces to move them, drag off the board to remove, or pick a piece below and click squares to place it.
      </p>
      <div className="space-y-1.5">
        {(["white", "black"] as const).map((color) => (
          <div key={color} className="flex flex-wrap gap-1.5" role="group" aria-label={`${color} pieces`}>
            {ROLES.map((role) => (
              <button
                key={role}
                type="button"
                aria-pressed={isActive({ role, color })}
                aria-label={`Place ${color} ${role}`}
                onClick={() => setPlacing(isActive({ role, color }) ? null : { role, color })}
                className={`h-11 w-11 rounded-lg p-1 transition outline-none focus-visible:ring-2 focus-visible:ring-ring ${isActive({ role, color }) ? "bg-accent ring-2 ring-accent" : "bg-[#f0d9b5] hover:brightness-95"}`}
              >
                <PieceIcon role={role} color={color} />
              </button>
            ))}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-1.5">
        <Button size="sm" variant={placing === "delete" ? "primary" : "secondary"} aria-pressed={placing === "delete"}
          onClick={() => setPlacing(placing === "delete" ? null : "delete")}>Eraser</Button>
        <Button size="sm" onClick={onClear}>Clear board</Button>
        <Button size="sm" onClick={onStart}>Start position</Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <fieldset>
          <legend className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Side to move</legend>
          <div className="inline-flex rounded-lg bg-surface-2 p-0.5">
            {(["w", "b"] as const).map((t) => (
              <label key={t} className={`cursor-pointer rounded-md px-3 py-1 text-sm ${state.turn === t ? "bg-surface shadow-sm" : "text-muted"}`}>
                <input type="radio" name="turn" className="sr-only" checked={state.turn === t} onChange={() => setState({ ...state, turn: t })} />
                {t === "w" ? "White" : "Black"}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-muted">En passant</span>
          <input value={state.ep} onChange={(e) => setState({ ...state, ep: e.target.value.trim().toLowerCase() })} placeholder="none"
            maxLength={2} className="w-20 rounded-lg border border-line bg-surface px-2 py-1 font-mono outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        </label>
      </div>
      <fieldset>
        <legend className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Castling rights</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {[["K", "White O-O"], ["Q", "White O-O-O"], ["k", "Black O-O"], ["q", "Black O-O-O"]].map(([c, text]) => (
            <label key={c} className="flex items-center gap-1.5">
              <input type="checkbox" className="accent-[var(--accent)]" checked={state.castling.includes(c)} onChange={() => toggleCastle(c)} />
              {text}
            </label>
          ))}
        </div>
      </fieldset>
    </div>
  );
}
