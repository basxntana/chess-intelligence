"use client";

import { AnalysisTab, ExplanationTab, InsightsTab, LiveProgress } from "@/components/AnalysisPanel";
import Board, { type BoardMode } from "@/components/Board";
import EvalBar from "@/components/EvalBar";
import History from "@/components/History";
import PositionEditor, { type EditState } from "@/components/PositionEditor";
import { Button, Card, Chip, Empty, PieceIcon, Spinner, Tabs } from "@/components/ui";
import { API, type Analysis, api, type Explanation, formatScore, type Validation } from "@/lib/api";
import type { DrawShape } from "chessground/draw";
import type { Color, Key, Piece } from "chessground/types";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const EMPTY = "4k3/8/8/8/8/8/8/4K3";
type Tab = "analysis" | "explain" | "insights" | "history";

export default function Home() {
  // Position being studied
  const [fen, setFen] = useState(START);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [lastMove, setLastMove] = useState<[Key, Key] | undefined>();
  const [undo, setUndo] = useState<string[]>([]);
  const [boardVersion, setBoardVersion] = useState(0); // remount the board to undo a rejected drag
  const [orientation, setOrientation] = useState<Color>("white");
  const [fenInput, setFenInput] = useState(START);
  const [promotion, setPromotion] = useState("q");

  // Editor
  const [mode, setMode] = useState<"play" | "edit">("play");
  const [placement, setPlacement] = useState(START.split(" ")[0]);
  const [edit, setEdit] = useState<EditState>({ turn: "w", castling: "KQkq", ep: "" });
  const [placing, setPlacing] = useState<Piece | "delete" | null>(null);

  // Analysis
  const [settings, setSettings] = useState({ depth: 5, candidates: 3, time_limit: 8 });
  const [name, setName] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [line, setLine] = useState(0);
  const [ply, setPly] = useState(0);
  const [hover, setHover] = useState<string[]>([]);
  const [history, setHistory] = useState<Analysis[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [tab, setTab] = useState<Tab>("analysis");
  const [online, setOnline] = useState<boolean | null>(null);
  const pollToken = useRef(0);

  const turn: Color = fen.split(" ")[1] === "b" ? "black" : "white";

  const refreshHistory = useCallback(() => api.history().then((h) => setHistory(h.items)).catch(() => {}), []);
  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));

  const loadPosition = useCallback(async (newFen: string, move?: [Key, Key]) => {
    const v = await api.validate(newFen);
    if (!v.legal) throw new Error(v.errors.join("; ") || "Illegal position");
    setFen(v.fen!);
    setFenInput(v.fen!);
    setValidation(v);
    setLastMove(move);
    pollToken.current++; // a running poll belongs to the old position
    setAnalysis(null);
    setExplanation(null);
    setPly(0);
    setLine(0);
    return v;
  }, []);

  useEffect(() => {
    loadPosition(START).catch(fail);
    refreshHistory();
    fetch(`${API}/health`).then((r) => r.json()).then((h) => setOnline(h.status === "ok" && h.database === "ok")).catch(() => setOnline(false));
  }, [loadPosition, refreshHistory]);

  // ---------- play mode ----------
  const onMove = async (orig: Key, dest: Key) => {
    const uci = validation?.legal_moves?.find((m) => m.startsWith(orig + dest) && (m.length === 4 || m[4] === promotion));
    if (!uci) return setBoardVersion((x) => x + 1);
    try {
      setError(null);
      const r = await api.move(fen, uci);
      setUndo((u) => [...u, fen]);
      await loadPosition(r.fen!, [orig, dest]);
    } catch (e) {
      fail(e);
      setBoardVersion((x) => x + 1);
    }
  };

  const back = () => {
    const prev = undo.at(-1);
    if (!prev) return;
    setUndo((u) => u.slice(0, -1));
    loadPosition(prev).catch(fail);
  };

  // ---------- editor ----------
  const startEdit = () => {
    const [p, t, c, e] = fen.split(" ");
    setPlacement(p);
    setEdit({ turn: t as "w" | "b", castling: c === "-" ? "" : c, ep: e === "-" ? "" : e });
    setMode("edit");
    pollToken.current++;
    setAnalysis(null);
    setError(null);
  };
  const finishEdit = async () => {
    const full = `${placement} ${edit.turn} ${edit.castling || "-"} ${edit.ep || "-"} 0 1`;
    try {
      setError(null);
      await loadPosition(full);
      setUndo([]);
      setMode("play");
      setPlacing(null);
    } catch (e) {
      fail(e); // stay in the editor so the user can fix the position
    }
  };

  // ---------- analysis ----------
  const runAnalysis = async () => {
    setError(null);
    setExplanation(null);
    setLine(0);
    setPly(0);
    setTab("analysis");
    const token = ++pollToken.current;
    try {
      let a = await api.analyze(fen, { ...settings, name: name.trim() || undefined });
      setAnalysis(a);
      const started = Date.now();
      while (a.status === "pending" || a.status === "running") {
        await new Promise((r) => setTimeout(r, 400));
        if (token !== pollToken.current) return; // superseded by a newer analysis or position change
        setElapsed((Date.now() - started) / 1000);
        a = await api.analysis(a.id);
        if (token === pollToken.current) setAnalysis(a); // show best-so-far progress while it runs
      }
      if (token !== pollToken.current) return;
      setAnalysis(a);
      setExplanation(a.result?.explanation ?? null);
      if (a.status === "failed") setError(`Analysis failed: ${a.error}`);
      refreshHistory();
    } catch (e) {
      fail(e);
    }
  };

  const explain = async (useLlm: boolean) => {
    if (!analysis) return;
    setExplaining(true);
    setError(null);
    try {
      setExplanation(await api.explain(analysis.id, { move: variation?.move, use_llm: useLlm }));
    } catch (e) {
      fail(e);
    } finally {
      setExplaining(false);
    }
  };

  const openHistory = async (id: string) => {
    try {
      setError(null);
      const a = await api.analysis(id);
      await loadPosition(a.fen);
      setUndo([]);
      setMode("play");
      setAnalysis(a);
      setExplanation(a.result?.explanation ?? null);
      setTab("analysis");
    } catch (e) {
      fail(e);
    }
  };

  const clearHistory = async () => {
    try {
      await api.clearHistory();
      setAnalysis(null);
      setExplanation(null);
      refreshHistory();
    } catch (e) {
      fail(e);
    }
  };

  // ---------- board view ----------
  const result = analysis?.status === "done" ? analysis.result : null;
  const variation = result?.variations[line];
  const viewing = !!(result && variation && ply > 0);
  const viewPly = viewing ? variation!.plies[ply - 1] : null;
  const busy = analysis?.status === "pending" || analysis?.status === "running";
  const progress = busy ? analysis?.progress ?? null : null; // best-so-far while the engine searches deeper
  const shapes = useMemo<DrawShape[]>(() => {
    if (viewing || mode === "edit") return [];
    const moves = result ? result.variations.map((v) => v.move) : progress ? progress.candidates.map((c) => c.move) : [];
    return moves.map((m, i) => ({
      orig: m.slice(0, 2) as Key,
      dest: m.slice(2, 4) as Key,
      brush: i === 0 ? "green" : "blue",
      modifiers: { lineWidth: i === 0 ? 12 : 6 },
    }));
  }, [result, progress, viewing, mode]);

  const boardMode: BoardMode = mode === "edit" ? "edit" : viewing ? "view" : "play";
  const boardFen = mode === "edit" ? placement : viewPly ? viewPly.fen : fen;
  const boardTurn: Color = viewPly ? (viewPly.fen.split(" ")[1] === "b" ? "black" : "white") : turn;
  const boardLast = viewPly ? ([viewPly.uci.slice(0, 2), viewPly.uci.slice(2, 4)] as [Key, Key]) : lastMove;
  const stm = result?.insights.side_to_move ?? turn;
  const toWhiteMate = (m: number | null | undefined) => (m == null ? null : stm === "white" ? m : -m);
  const live = progress?.candidates[0];
  const barScore = result?.search.score_white ?? live?.score_white ?? 0;
  const mateWhite = result ? toWhiteMate(result.search.mate_in) : toWhiteMate(live?.mate_in);
  const barLabel = result
    ? formatScore(result.search.score_white, result.search.mate_in, stm)
    : live ? formatScore(live.score_white, live.mate_in, stm) : "0.0";
  const sideToMove = mode === "edit" ? (edit.turn === "w" ? "white" : "black") : boardTurn;

  const PlayerStrip = ({ color }: { color: Color }) => (
    <div className="flex items-center gap-2 px-1 text-sm">
      <span className={`h-3.5 w-3.5 rounded-full border border-line ${color === "white" ? "bg-white" : "bg-neutral-900"}`} />
      <span className="font-medium capitalize">{color}</span>
      {sideToMove === color && <Chip tone="accent">to move</Chip>}
      {color === turn && !viewing && mode === "play" && validation?.in_check && <Chip tone="bad">check</Chip>}
    </div>
  );

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-line bg-surface/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent p-1 shadow-sm"><PieceIcon role="knight" color="white" /></span>
          <div className="min-w-0">
            <h1 className="text-lg font-semibold leading-tight">Chess Intelligence</h1>
            <p className="truncate text-xs text-muted">Custom engine · grounded explanations</p>
          </div>
          <span className="ml-auto flex items-center gap-1.5 text-xs text-muted" role="status">
            <span className={`h-2 w-2 rounded-full ${online === null ? "bg-neutral-400" : online ? "bg-good" : "bg-bad"}`} />
            {online === null ? "Connecting…" : online ? "Engine online" : "Engine offline"}
          </span>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 p-4 lg:grid-cols-[minmax(0,600px)_minmax(0,1fr)] lg:p-6">
        <div className="space-y-4">
          <Card className="space-y-2">
            <PlayerStrip color={orientation === "white" ? "black" : "white"} />
            <div className="flex gap-2">
              <EvalBar
                scoreWhite={barScore}
                mateWhite={mateWhite}
                flipped={orientation === "black"}
                label={barLabel}
              />
              <div className="min-w-0 flex-1">
                <Board
                  key={boardVersion}
                  fen={boardFen}
                  mode={boardMode}
                  orientation={orientation}
                  turn={boardTurn}
                  legalMoves={validation?.legal_moves}
                  lastMove={boardLast}
                  check={!viewing && mode === "play" && !!validation?.in_check}
                  shapes={shapes}
                  highlight={hover}
                  placing={placing}
                  onMove={onMove}
                  onEdit={setPlacement}
                />
              </div>
            </div>
            <PlayerStrip color={orientation} />
            {viewing && (
              <p className="rounded-lg bg-accent-soft px-2 py-1 text-xs text-accent">
                Exploring {variation!.plies[0].san} line, move {ply} of {variation!.plies.length}. The board is read-only.
              </p>
            )}
          </Card>

          <div className="flex flex-wrap items-center gap-2">
            {mode === "play" ? (
              <>
                <Button key="undo" onClick={back} disabled={!undo.length}>↶ Undo</Button>
                <Button key="reset" onClick={() => { loadPosition(START).catch(fail); setUndo([]); }}>Reset</Button>
                <Button key="edit" onClick={startEdit}>✎ Edit position</Button>
              </>
            ) : (
              <>
                <Button key="done" variant="primary" onClick={finishEdit}>Done editing</Button>
                <Button key="cancel" variant="ghost" onClick={() => { setMode("play"); setPlacing(null); setError(null); }}>Cancel</Button>
              </>
            )}
            <Button onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}>⇅ Flip</Button>
            <label className="ml-auto flex items-center gap-1.5 text-sm text-muted">
              Promote to
              <select value={promotion} onChange={(e) => setPromotion(e.target.value)}
                className="rounded-lg border border-line bg-surface px-2 py-1 text-fg outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <option value="q">Queen</option>
                <option value="r">Rook</option>
                <option value="b">Bishop</option>
                <option value="n">Knight</option>
              </select>
            </label>
          </div>

          {mode === "edit" && (
            <Card title="Edit position">
              <PositionEditor
                placing={placing}
                setPlacing={setPlacing}
                state={edit}
                setState={setEdit}
                onClear={() => { setPlacement(EMPTY); setEdit({ ...edit, castling: "", ep: "" }); }}
                onStart={() => { setPlacement(START.split(" ")[0]); setEdit({ turn: "w", castling: "KQkq", ep: "" }); }}
              />
            </Card>
          )}

          <Card title="Position">
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                loadPosition(fenInput.trim()).then(() => { setUndo([]); setMode("play"); setError(null); }).catch(fail);
              }}
            >
              <label htmlFor="fen" className="sr-only">FEN</label>
              <input id="fen" value={fenInput} onChange={(e) => setFenInput(e.target.value)} spellCheck={false}
                className="min-w-0 flex-1 rounded-lg border border-line bg-surface-2 px-2 py-1.5 font-mono text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring" />
              <Button type="submit">Load FEN</Button>
            </form>
            <p className="mt-2 text-xs text-muted">
              {validation?.status ?? "…"} · {validation?.legal_moves?.length ?? 0} legal moves
            </p>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <div className="flex flex-wrap items-end gap-3">
              {([["depth", "Depth", 1, 8], ["candidates", "Lines", 1, 5], ["time_limit", "Time (s)", 1, 30]] as const).map(([key, text, min, max]) => (
                <label key={key} className="flex flex-col gap-1">
                  <span className="text-xs text-muted">{text}</span>
                  <input type="number" min={min} max={max} value={settings[key]}
                    onChange={(e) => setSettings({ ...settings, [key]: Math.min(max, Math.max(min, Number(e.target.value) || min)) })}
                    className="w-20 rounded-lg border border-line bg-surface-2 px-2 py-1.5 font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" />
                </label>
              ))}
              <label className="flex min-w-40 flex-1 flex-col gap-1">
                <span className="text-xs text-muted">Name (optional)</span>
                <input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="e.g. My Sicilian idea"
                  className="rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" />
              </label>
              <Button variant="primary" onClick={runAnalysis} disabled={mode === "edit" || busy} className="h-9 px-5">
                {busy ? <Spinner label={`Analyzing ${elapsed.toFixed(1)}s`} /> : "Analyze"}
              </Button>
            </div>
          </Card>

          {error && (
            <p role="alert" className="rounded-xl border border-bad/40 bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>
          )}

          <Tabs<Tab>
            value={tab}
            onChange={setTab}
            tabs={[
              { id: "analysis", label: "Analysis" },
              { id: "explain", label: "Explanation" },
              { id: "insights", label: "Insights" },
              { id: "history", label: "History", badge: history.length ? <Chip>{history.length}</Chip> : undefined },
            ]}
          />
          <Card>
            <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
              {tab === "history" ? (
                <History
                  items={history}
                  activeId={analysis?.id ?? null}
                  onOpen={openHistory}
                  onRename={(id, n) => api.rename(id, n).then(refreshHistory).catch(fail)}
                  onDelete={(id) => api.remove(id).then(() => { if (analysis?.id === id) setAnalysis(null); refreshHistory(); }).catch(fail)}
                  onClearAll={clearHistory}
                />
              ) : busy ? (
                <LiveProgress progress={progress} stm={stm} elapsed={elapsed} />
              ) : !result ? (
                <Empty>Set up a position and press <strong>Analyze</strong>. The engine&apos;s moves, explanation and insights appear here.</Empty>
              ) : tab === "analysis" ? (
                <AnalysisTab result={result} line={line} ply={ply} setLine={setLine} setPly={setPly} />
              ) : tab === "explain" ? (
                <ExplanationTab explanation={explanation} explaining={explaining} moveSan={variation?.plies[0]?.san} onExplain={explain} />
              ) : (
                <InsightsTab result={result} onHover={setHover} />
              )}
            </div>
          </Card>
        </div>
      </main>
    </div>
  );
}
