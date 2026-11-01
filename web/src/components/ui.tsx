import Link from "next/link";

const categoryColour: Record<string, string> = {
  health: "var(--color-cat-health)",
  education: "var(--color-cat-education)",
  environment: "var(--color-cat-environment)",
  water: "var(--color-cat-water)",
};

export function CategoryBadge({ id }: { id: string }) {
  const colour = categoryColour[id] ?? "var(--color-muted)";
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium capitalize"
      style={{ color: colour, backgroundColor: `color-mix(in srgb, ${colour} 10%, white)` }}
    >
      <span className="size-1.5 rounded-full" style={{ backgroundColor: colour }} aria-hidden />
      {id}
    </span>
  );
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      className="h-2 overflow-hidden rounded-full bg-line"
    >
      <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function UrgencyBadge({ level }: { level: number }) {
  if (level < 4) return null;
  return (
    <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-accent">Urgent</span>
  );
}

export function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="tabular text-2xl font-semibold">{value}</div>
      <div className="text-sm text-muted">{label}</div>
    </div>
  );
}

/** Empty state: always says what happened and offers a next step (heuristic H1) */
export function EmptyState({ title, body, action }: { title: string; body: string; action?: { href: string; label: string } }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-surface p-10 text-center">
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-sm text-muted">{body}</p>
      {action && (
        <Link href={action.href} className="mt-4 inline-flex min-h-11 items-center rounded-lg px-4 font-medium text-primary hover:bg-primary-soft">
          {action.label}
        </Link>
      )}
    </div>
  );
}
