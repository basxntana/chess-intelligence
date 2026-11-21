export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Validation = {
  syntax_valid: boolean;
  legal: boolean;
  errors: string[];
  fen?: string;
  status?: string;
  in_check?: boolean;
  legal_moves?: string[];
};

export type Sentence = { text: string; facts: string[] };
export type Explanation = {
  move: string;
  san: string;
  source: "rule_based" | "llm";
  model: string | null;
  summary: Sentence;
  details: Sentence[];
  tactical_warnings: Sentence[];
  strategic_summary: Sentence[];
  candidate_comparison: Sentence[];
  grounding: { valid: boolean; fallback_reason: string | null };
};

export type Tactic = {
  motif: string;
  by: string;
  against: string;
  squares: string[];
  severity: number;
  verified: boolean | null;
};
export type Strategic = { category: string; feature: string; side: string; squares: string[]; score: number };
export type CandidateInsight = {
  move: string;
  score: number;
  mate_in: number | null;
  pv: string[];
  tactics: Tactic[];
  eval_change: Record<string, number>;
};
export type Ply = { ply: number; uci: string; san: string; fen: string };
export type Variation = { move: string; score: number; mate_in: number | null; plies: Ply[] };

export type AnalysisResult = {
  search: {
    best_move: string | null;
    score: number;
    score_white: number;
    mate_in: number | null;
    pv: string[];
    depth: number;
    nodes: number;
    time: number;
    nps: number;
    terminal: string | null;
  };
  evaluation: { score: number; phase: number; terms: Record<string, { score: number }> };
  insights: {
    side_to_move: "white" | "black";
    position: { tactics: Tactic[]; strategic: Strategic[] };
    candidates: CandidateInsight[];
  };
  variations: Variation[];
  explanation: Explanation | null;
};

export type Progress = {
  depth: number;
  nodes: number;
  seconds: number;
  candidates: { move: string; san: string; score_white: number; mate_in: number | null; pv_san: string[] }[];
};

export type Analysis = {
  id: string;
  name: string | null;
  fen: string;
  status: "pending" | "running" | "done" | "failed";
  error: string | null;
  depth: number;
  candidates: number;
  best_move: string | null;
  evaluation_score: number | null;
  mate_in: number | null;
  created_at: string;
  completed_at: string | null;
  result?: AnalysisResult | null;
  progress?: Progress | null;
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (r.status === 204) return undefined as T;
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    const detail = body?.detail;
    const msg = Array.isArray(detail) ? detail.map((d) => (typeof d === "string" ? d : d.msg)).join("; ") : detail;
    throw new Error(msg || `API error ${r.status}`);
  }
  return body as T;
}

const post = <T>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  validate: (fen: string) => post<Validation>("/positions/validate", { fen }),
  move: (fen: string, move: string) => post<Validation & { san: string }>("/positions/move", { fen, move }),
  analyze: (fen: string, opts: { depth: number; candidates: number; time_limit: number; name?: string }) =>
    post<Analysis>("/analysis", { fen, ...opts }),
  analysis: (id: string) => call<Analysis>(`/analysis/${id}`),
  explain: (id: string, body: { move?: string; use_llm?: boolean; language?: string }) =>
    post<Explanation>(`/analysis/${id}/explain`, body),
  history: () => call<{ total: number; items: Analysis[] }>("/history?limit=100"),
  rename: (id: string, name: string) => call<Analysis>(`/history/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  remove: (id: string) => call<void>(`/history/${id}`, { method: "DELETE" }),
  clearHistory: () => call<{ deleted: number }>("/history", { method: "DELETE" }),
};

/** White-perspective display score: "+1.25", "#3" (White mates) or "#-2" (Black mates). */
export function formatScore(scoreWhite: number, mateIn: number | null, sideToMove: "white" | "black"): string {
  if (mateIn !== null) {
    const forWhite = sideToMove === "white" ? mateIn : -mateIn;
    return `#${forWhite}`;
  }
  return `${scoreWhite >= 0 ? "+" : ""}${(scoreWhite / 100).toFixed(2)}`;
}
