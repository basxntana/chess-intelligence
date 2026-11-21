"use client";

import { type Analysis, formatScore } from "@/lib/api";
import { useState } from "react";
import { Button, Chip, Empty } from "./ui";

type Props = {
  items: Analysis[];
  activeId: string | null;
  onOpen: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
  onClearAll: () => void;
};

export default function History({ items, activeId, onOpen, onRename, onDelete, onClearAll }: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null); // an id, or "all"

  if (!items.length) return <Empty>No saved analyses yet. Every analysis you run is saved here.</Empty>;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted">{items.length} saved {items.length === 1 ? "analysis" : "analyses"}</p>
        {confirming === "all" ? (
          <span className="flex items-center gap-1.5 text-xs" role="group" aria-label="Confirm clearing history">
            <span className="text-bad">Delete all {items.length}?</span>
            <Button size="sm" variant="danger" onClick={() => { onClearAll(); setConfirming(null); }}>Yes, delete all</Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>Cancel</Button>
          </span>
        ) : (
          <Button size="sm" variant="danger" onClick={() => setConfirming("all")}>Clear history</Button>
        )}
      </div>

      <ul className="space-y-1.5">
        {items.map((a) => {
          const stm = a.fen.split(" ")[1] === "b" ? "black" : "white";
          const active = a.id === activeId;
          return (
            <li key={a.id} className={`rounded-xl border px-3 py-2 ${active ? "border-accent bg-accent-soft" : "border-line"}`}>
              {editing === a.id ? (
                <form className="flex gap-1.5" onSubmit={(e) => { e.preventDefault(); if (draft.trim()) onRename(a.id, draft.trim()); setEditing(null); }}>
                  <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={120} aria-label="Analysis name"
                    className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-2 py-1 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" />
                  <Button size="sm" variant="primary" type="submit">Save</Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
                </form>
              ) : (
                <div className="flex items-center gap-2">
                  <button type="button" onClick={() => onOpen(a.id)} className="min-w-0 flex-1 rounded-md text-left outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    <span className="block truncate text-sm font-medium">{a.name || "Untitled position"}</span>
                    <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
                      {a.status === "done" && a.evaluation_score !== null ? (
                        <span className="font-mono text-fg">{a.best_move} {formatScore(a.evaluation_score, a.mate_in, stm)}</span>
                      ) : <Chip tone={a.status === "failed" ? "bad" : "neutral"}>{a.status}</Chip>}
                      <span>· depth {a.depth}</span>
                      <span>· {new Date(a.created_at).toLocaleString()}</span>
                    </span>
                  </button>
                  {confirming === a.id ? (
                    <span className="flex gap-1" role="group" aria-label="Confirm delete">
                      <Button size="sm" variant="danger" onClick={() => { onDelete(a.id); setConfirming(null); }}>Delete</Button>
                      <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>Keep</Button>
                    </span>
                  ) : (
                    <span className="flex gap-0.5">
                      <Button size="sm" variant="ghost" aria-label={`Rename ${a.name ?? "analysis"}`} onClick={() => { setEditing(a.id); setDraft(a.name ?? ""); }}>Rename</Button>
                      <Button size="sm" variant="ghost" className="hover:text-bad" aria-label={`Delete ${a.name ?? "analysis"}`} onClick={() => setConfirming(a.id)}>Delete</Button>
                    </span>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
