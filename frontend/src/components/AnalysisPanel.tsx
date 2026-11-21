"use client";

import { type AnalysisResult, type Explanation, formatScore, type Progress, type Sentence, type Strategic } from "@/lib/api";
import { Button, Chip, Empty, Spinner } from "./ui";

const label = (s: string) => s.replaceAll("_", " ");
const STRATEGIC_SHOWN = new Set([
  "material_balance", "exchange_up", "piece_vs_pawns", "queen_vs_rooks", "passed_pawn", "isolated_pawn",
  "doubled_pawns", "pawn_shield", "open_files_near_king", "king_zone_attacked", "bishop_pair", "rook_open_file",
  "passive_piece", "mobility", "center_attacks",
]);

/** Engine result, candidate comparison and the move explorer. */
export function AnalysisTab({ result, line, ply, setLine, setPly }:
  { result: AnalysisResult; line: number; ply: number; setLine: (i: number) => void; setPly: (i: number) => void }) {
  const s = result.search;
  const stm = result.insights.side_to_move;
  const toWhite = (score: number) => (stm === "white" ? score : -score);
  if (s.terminal) return <Empty>The game is over in this position: {s.terminal}.</Empty>;
  const variation = result.variations[line];
  const best = result.variations[0]?.plies[0]?.san ?? "–";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs text-muted">Best move</p>
          <p className="font-mono text-3xl font-semibold tracking-tight">{best}</p>
        </div>
        <div className="text-right">
          <p className="text-xs text-muted">Evaluation (White)</p>
          <p className="font-mono text-3xl font-semibold tracking-tight">{formatScore(s.score_white, s.mate_in, stm)}</p>
        </div>
      </div>
      <dl className="grid grid-cols-4 gap-2 text-center">
        {[["Depth", s.depth], ["Nodes", s.nodes.toLocaleString()], ["Time", `${s.time.toFixed(2)}s`], ["Speed", `${(s.nps / 1000).toFixed(1)}k/s`]].map(([k, v]) => (
          <div key={k} className="rounded-xl bg-surface-2 px-2 py-1.5">
            <dt className="text-[11px] text-muted">{k}</dt>
            <dd className="font-mono text-sm font-medium">{v}</dd>
          </div>
        ))}
      </dl>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Candidate moves</h3>
        <ul className="space-y-1.5">
          {result.variations.map((v, i) => {
            const insight = result.insights.candidates.find((c) => c.move === v.move);
            const motifs = insight?.tactics.filter((t) => !["check", "material_gain"].includes(t.motif)) ?? [];
            const active = line === i;
            return (
              <li key={v.move}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => { setLine(i); setPly(1); }}
                  className={`w-full rounded-xl border px-3 py-2 text-left transition outline-none focus-visible:ring-2 focus-visible:ring-ring ${active ? "border-accent bg-accent-soft" : "border-line hover:bg-surface-2"}`}
                >
                  <div className="flex items-center gap-3">
                    <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${i === 0 ? "bg-good/15 text-good" : "bg-surface-2 text-muted"}`}>{i + 1}</span>
                    <span className="w-14 font-mono font-semibold">{v.plies[0]?.san}</span>
                    <span className="w-16 font-mono text-sm">{formatScore(toWhite(v.score), v.mate_in, stm)}</span>
                    <span className="flex flex-wrap gap-1">{motifs.map((t) => <Chip key={t.motif + t.squares.join()} tone="accent">{label(t.motif)}</Chip>)}</span>
                  </div>
                  <p className="mt-1 truncate pl-9 font-mono text-xs text-muted">{v.plies.map((x) => x.san).join(" ")}</p>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {variation && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Move explorer</h3>
          <div className="rounded-xl bg-surface-2 p-2">
            <div className="flex flex-wrap items-center gap-0.5 font-mono text-sm">
              {variation.plies.map((x) => (
                <button key={x.ply} type="button" onClick={() => setPly(x.ply)} aria-current={ply === x.ply}
                  className={`rounded-md px-1.5 py-0.5 outline-none focus-visible:ring-2 focus-visible:ring-ring ${ply === x.ply ? "bg-accent text-accent-fg" : "hover:bg-surface"}`}>
                  {(x.ply % 2 === 1) === (stm === "white") && (
                    <span className="mr-0.5 opacity-60">{stm === "white" ? Math.ceil(x.ply / 2) : x.ply / 2 + 1}.</span>
                  )}
                  {x.ply === 1 && stm === "black" && <span className="mr-0.5 opacity-60">1…</span>}
                  {x.san}
                </button>
              ))}
            </div>
            <div className="mt-2 flex items-center gap-1" role="group" aria-label="Explorer navigation">
              {([["⏮", 0, "Start"], ["◀", Math.max(0, ply - 1), "Back"], ["▶", Math.min(variation.plies.length, ply + 1), "Forward"], ["⏭", variation.plies.length, "End"]] as const).map(([icon, target, name]) => (
                <Button key={name} size="sm" aria-label={name} onClick={() => setPly(target)}>{icon}</Button>
              ))}
              <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setPly(0)} disabled={ply === 0}>Return to position</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const SECTIONS: [keyof Explanation, string][] = [
  ["details", "Why"],
  ["tactical_warnings", "Watch out"],
  ["strategic_summary", "Strategy"],
  ["candidate_comparison", "Alternatives"],
];

export function ExplanationTab({ explanation, explaining, moveSan, onExplain }:
  { explanation: Explanation | null; explaining: boolean; moveSan: string | undefined; onExplain: (useLlm: boolean) => void }) {
  return (
    <div className="space-y-4" aria-live="polite">
      {explanation ? (
        <>
          <div className="rounded-xl border-l-4 border-accent bg-accent-soft/60 px-3 py-2">
            <p className="font-medium leading-relaxed">{explanation.summary.text}</p>
          </div>
          {SECTIONS.map(([key, title]) => {
            const items = explanation[key] as Sentence[];
            return items.length ? (
              <div key={key}>
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">{title}</h3>
                <ul className="space-y-1 text-sm leading-relaxed">
                  {items.map((x) => <li key={x.text} className="flex gap-2"><span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />{x.text}</li>)}
                </ul>
              </div>
            ) : null;
          })}
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <Chip tone={explanation.source === "llm" ? "accent" : "neutral"}>
              {explanation.source === "llm" ? `Claude · ${explanation.model}` : "Rule-based"}
            </Chip>
            <span>Every sentence is checked against the engine&apos;s facts.</span>
            {explanation.grounding.fallback_reason && <span className="w-full">Claude not used: {explanation.grounding.fallback_reason}</span>}
          </div>
        </>
      ) : <Empty>No explanation yet.</Empty>}
      <div className="flex flex-wrap gap-2 border-t border-line pt-3">
        <Button disabled={explaining} onClick={() => onExplain(false)}>Explain {moveSan ?? "best move"}</Button>
        <Button variant="primary" disabled={explaining} onClick={() => onExplain(true)}>
          {explaining ? <Spinner label="Explaining…" /> : "✦ Ask Claude"}
        </Button>
      </div>
    </div>
  );
}

export function InsightsTab({ result, onHover }: { result: AnalysisResult; onHover: (squares: string[]) => void }) {
  const tactics = result.insights.position.tactics;
  const strategic = result.insights.position.strategic.filter((f: Strategic) => STRATEGIC_SHOWN.has(f.feature));
  const row = (key: string, side: string, text: string, squares: string[]) => (
    <li key={key} tabIndex={0} onMouseEnter={() => onHover(squares)} onMouseLeave={() => onHover([])}
      onFocus={() => onHover(squares)} onBlur={() => onHover([])}
      className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm outline-none hover:bg-surface-2 focus-visible:ring-2 focus-visible:ring-ring">
      <span aria-label={side} className={`h-3 w-3 shrink-0 rounded-full border border-line ${side === "white" ? "bg-white" : side === "black" ? "bg-neutral-900" : "bg-gradient-to-r from-white to-neutral-900"}`} />
      <span className="flex-1 capitalize">{text}</span>
      {squares.length > 0 && <span className="font-mono text-xs text-muted">{squares.join(" ")}</span>}
    </li>
  );
  return (
    <div className="space-y-5">
      <p className="text-xs text-muted">Hover an item to highlight its squares on the board.</p>
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Tactics on the board</h3>
        {tactics.length
          ? <ul>{tactics.map((t, i) => row(`t${i}`, t.by, label(t.motif), t.squares))}</ul>
          : <Empty>No tactics found in this position.</Empty>}
      </div>
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Strategic features</h3>
        <ul>
          {strategic.map((f, i) => row(`s${i}`, f.side,
            label(f.feature) + (f.feature === "material_balance" && f.score ? ` (+${(f.score / 100).toFixed(1)})` : ""), f.squares))}
        </ul>
      </div>
    </div>
  );
}

/** Best-so-far result while the search continues (one update per completed depth). */
export function LiveProgress({ progress, stm, elapsed }: { progress: Progress | null; stm: "white" | "black"; elapsed: number }) {
  const best = progress?.candidates[0];
  return (
    <div className="space-y-4" aria-live="polite">
      <div className="flex items-center justify-between gap-2 text-sm text-muted">
        <Spinner label={progress ? `Thinking deeper… depth ${progress.depth} done` : "Starting the engine…"} />
        <span className="font-mono text-xs">{elapsed.toFixed(1)}s</span>
      </div>
      {best ? (
        <>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-xs text-muted">Best so far</p>
              <p className="font-mono text-3xl font-semibold tracking-tight">{best.san}</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-muted">Evaluation (White)</p>
              <p className="font-mono text-3xl font-semibold tracking-tight">{formatScore(best.score_white, best.mate_in, stm)}</p>
            </div>
          </div>
          <ul className="space-y-1.5">
            {progress!.candidates.map((c, i) => (
              <li key={c.move} className="flex items-center gap-3 rounded-xl border border-line px-3 py-2 text-sm">
                <span className="w-5 text-xs text-muted">{i + 1}</span>
                <span className="w-14 font-mono font-semibold">{c.san}</span>
                <span className="w-16 font-mono">{formatScore(c.score_white, c.mate_in, stm)}</span>
                <span className="truncate font-mono text-xs text-muted">{c.pv_san.join(" ")}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted">
            Moves can still change as the search goes deeper ({progress!.nodes.toLocaleString()} positions so far).
            Tactics and the explanation appear when the analysis finishes.
          </p>
        </>
      ) : <div className="h-24 animate-pulse rounded-xl bg-surface-2" />}
    </div>
  );
}
