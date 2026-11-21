"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANT: Record<Variant, string> = {
  primary: "bg-accent text-accent-fg hover:brightness-110 shadow-sm",
  secondary: "border border-line bg-surface text-fg hover:bg-surface-2",
  ghost: "text-muted hover:bg-surface-2 hover:text-fg",
  danger: "border border-bad/40 text-bad hover:bg-bad-soft",
};

export function Button({ variant = "secondary", size = "md", className = "", ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-45 ${size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm"} ${VARIANT[variant]} ${className}`}
    />
  );
}

export function Card({ title, actions, children, className = "" }:
  { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-line bg-surface p-4 shadow-sm ${className}`}>
      {(title || actions) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "accent" | "bad" }) {
  const cls = tone === "accent" ? "bg-accent-soft text-accent" : tone === "bad" ? "bg-bad-soft text-bad" : "bg-surface-2 text-muted";
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${cls}`}>{children}</span>;
}

export function Spinner({ label }: { label: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2">
      <span aria-hidden className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      <span>{label}</span>
    </span>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }:
  { tabs: { id: T; label: string; badge?: ReactNode }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div role="tablist" aria-label="Panels" className="flex gap-1 rounded-xl bg-surface-2 p-1">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          id={`tab-${t.id}`}
          aria-selected={value === t.id}
          aria-controls={`panel-${t.id}`}
          onClick={() => onChange(t.id)}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium transition outline-none focus-visible:ring-2 focus-visible:ring-ring ${value === t.id ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg"}`}
        >
          {t.label}
          {t.badge}
        </button>
      ))}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-xl border border-dashed border-line px-3 py-6 text-center text-sm text-muted">{children}</p>;
}

const ROLES = new Set(["king", "queen", "rook", "bishop", "knight", "pawn"]);

/** A piece image from the board's own (cburnett) set, sized by its parent. Chessground styles a <piece> element,
 *  which React would flag as unknown, so it is injected as static markup (role/color are from a fixed list). */
export function PieceIcon({ role, color }: { role: string; color: "white" | "black" }) {
  if (!ROLES.has(role)) return null;
  return (
    <span aria-hidden className="cg-wrap block h-full w-full" dangerouslySetInnerHTML={{
      __html: `<piece class="${role} ${color === "white" ? "white" : "black"}" style="position:static;display:block;width:100%;height:100%"></piece>`,
    }} />
  );
}
