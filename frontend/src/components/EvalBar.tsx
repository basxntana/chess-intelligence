/** Vertical evaluation bar, White at the bottom. `scoreWhite` in centipawns; `mateWhite` > 0 means White mates. */
export default function EvalBar({ scoreWhite, mateWhite, label, flipped }:
  { scoreWhite: number; mateWhite: number | null; label: string; flipped?: boolean }) {
  const white =
    mateWhite !== null ? (mateWhite > 0 ? 100 : 0) : 50 + 50 * (2 / (1 + Math.exp(-0.004 * scoreWhite)) - 1);
  const whiteAhead = white >= 50;
  return (
    <div
      className={`relative w-7 shrink-0 self-stretch overflow-hidden rounded-lg bg-neutral-800 ring-1 ring-line ${flipped ? "rotate-180" : ""}`}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(white)}
      aria-label={`Evaluation ${label}`}
      title={`Evaluation ${label}`}
    >
      <div className="absolute bottom-0 w-full bg-neutral-50 transition-[height] duration-700 ease-out" style={{ height: `${white}%` }} />
      <div aria-hidden className="absolute top-1/2 h-px w-full bg-amber-500/60" />
      <span
        className={`absolute inset-x-0 text-center font-mono text-[10px] font-semibold ${flipped ? "rotate-180" : ""} ${whiteAhead ? "text-neutral-700" : "text-neutral-200"}`}
        style={whiteAhead ? { bottom: 4 } : { top: 4 }} // the container's rotation already handles a flipped board
      >
        {label}
      </span>
    </div>
  );
}
