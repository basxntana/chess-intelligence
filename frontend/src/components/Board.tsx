"use client";

import { Chessground } from "chessground";
import "chessground/assets/chessground.base.css";
import "chessground/assets/chessground.cburnett.css";
import type { Api } from "chessground/api";
import type { DrawShape } from "chessground/draw";
import type { Color, Key, Piece } from "chessground/types";
import { useEffect, useRef } from "react";

export type BoardMode = "play" | "edit" | "view";

type Props = {
  fen: string; // full FEN; only the placement is shown
  mode: BoardMode;
  orientation: Color;
  turn: Color;
  legalMoves?: string[]; // UCI, play mode only
  lastMove?: [Key, Key];
  check?: boolean;
  shapes?: DrawShape[];
  highlight?: string[]; // squares to mark (e.g. a hovered tactic)
  placing?: Piece | "delete" | null; // edit mode: click a square to place/remove this
  onMove?: (orig: Key, dest: Key) => void;
  onEdit?: (placement: string) => void;
};

function dests(moves: string[] = []): Map<Key, Key[]> {
  const out = new Map<Key, Key[]>();
  for (const m of moves) {
    const from = m.slice(0, 2) as Key;
    const to = m.slice(2, 4) as Key;
    if (!out.get(from)?.includes(to)) out.set(from, [...(out.get(from) ?? []), to]);
  }
  return out;
}

export default function Board(props: Props) {
  const el = useRef<HTMLDivElement>(null);
  const cg = useRef<Api | null>(null);
  const latest = useRef(props);
  latest.current = props;

  useEffect(() => {
    if (!el.current) return;
    cg.current = Chessground(el.current, {
      events: {
        // Read handlers through a ref so the board is created once but always calls the current props.
        move: (orig, dest) => {
          const p = latest.current;
          if (p.mode === "play") p.onMove?.(orig, dest);
          else if (p.mode === "edit") p.onEdit?.(cg.current!.getFen());
        },
        select: (key) => {
          const p = latest.current;
          if (p.mode !== "edit" || !p.placing || !cg.current) return;
          cg.current.setPieces(new Map([[key, p.placing === "delete" ? undefined : p.placing]]));
          p.onEdit?.(cg.current.getFen());
        },
      },
    });
    return () => cg.current?.destroy();
  }, []);

  const { fen, mode, orientation, turn, legalMoves, lastMove, check, shapes, highlight, placing } = props;
  useEffect(() => {
    if (!cg.current) return;
    const edit = mode === "edit";
    cg.current.set({
      fen: fen.split(" ")[0],
      orientation,
      turnColor: turn,
      lastMove: lastMove ?? [],
      check: check ? turn : false,
      viewOnly: mode === "view",
      movable: {
        free: edit,
        color: edit ? "both" : mode === "play" ? turn : undefined,
        dests: edit ? undefined : dests(legalMoves),
        showDests: true,
      },
      draggable: { enabled: !(edit && placing), deleteOnDropOff: edit },
      selectable: { enabled: !(edit && placing) },
      highlight: { lastMove: true, check: true, custom: new Map((highlight ?? []).map((s) => [s as Key, "ci-mark"])) },
      drawable: { autoShapes: shapes ?? [] },
    });
  }, [fen, mode, orientation, turn, legalMoves, lastMove, check, shapes, highlight, placing]);

  return (
    <div className="ci-frame w-full max-w-[min(100%,560px)]">
      <div ref={el} className="aspect-square w-full" aria-label="Chess board" role="application" />
    </div>
  );
}
