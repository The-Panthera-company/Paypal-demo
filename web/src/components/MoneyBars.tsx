// "Where your money went": one card-row per project with a photo, a stacked bar (your gift +
// the matching it unlocked, on one scale) and the multiplier. Reused wherever we show money per project.
import { CategoryArt } from "./ui";

export type MoneyRow = { title: string; given: number; match: number; photo?: string; categoryId?: string; seed?: string; href?: string };

export function MoneyBars({ rows, format, givenLabel = "You gave", matchLabel = "Matching unlocked" }: { rows: MoneyRow[]; format: (cents: number) => string; givenLabel?: string; matchLabel?: string }) {
  const max = Math.max(1, ...rows.map((r) => r.given + r.match));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-5 text-sm text-ink" aria-hidden>
        <span className="flex items-center gap-2"><span className="h-3 w-6 bg-primary" /> {givenLabel}</span>
        <span className="flex items-center gap-2"><span className="h-3 w-6 bg-cobalt-green" /> {matchLabel}</span>
      </div>
      <ul className="space-y-3">
        {rows.map((r) => {
          const x = r.given > 0 ? (r.given + r.match) / r.given : 0;
          return (
            <li key={r.title} className="grid grid-cols-[56px_1fr] items-center gap-4 border border-line bg-white p-3 sm:grid-cols-[72px_1fr_auto]">
              <div className="size-14 overflow-hidden sm:size-[72px]">
                <CategoryArt id={r.categoryId ?? "people"} seed={r.seed ?? r.title} photo={r.photo} tint={false} label="" />
              </div>
              <div className="min-w-0 space-y-2">
                <p className="truncate font-medium text-ink">{r.title}</p>
                <div className="flex h-3 w-full overflow-hidden bg-surface-alt" role="img" aria-label={`${givenLabel} ${format(r.given)}, ${matchLabel.toLowerCase()} ${format(r.match)}`}>
                  <span className="h-full bg-primary" style={{ width: `${(r.given / max) * 100}%`, minWidth: r.given ? 4 : 0 }} />
                  <span className="h-full bg-cobalt-green" style={{ width: `${(r.match / max) * 100}%` }} />
                </div>
                <p className="tabular text-sm text-text">
                  <strong className="text-ink">{format(r.given)}</strong> given · <strong className="text-ink">{format(r.match)}</strong> matched
                </p>
              </div>
              <div className="col-span-2 sm:col-span-1 sm:text-right">
                {x >= 1.05 ? (
                  <span className="inline-block bg-accent px-3 py-1 font-display text-2xl text-ink">×{x >= 10 ? Math.round(x) : x.toFixed(1)}</span>
                ) : (
                  <span className="inline-block text-xs text-text">match projected<br className="max-sm:hidden" /> when the round fills</span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
