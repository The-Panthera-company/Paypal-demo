import Link from "next/link";

const art: Record<string, { from: string; to: string; label: string }> = {
  health: { from: "#c2410c", to: "#7c2d12", label: "Health" },
  education: { from: "#5a3fe4", to: "#4319cc", label: "Education" },
  environment: { from: "#15803d", to: "#14532d", label: "Environment" },
  water: { from: "#0e7490", to: "#164e63", label: "Water" },
};

/** Placeholder image until projects have real photos (from Person 3's seed data) */
export function CategoryArt({ id }: { id: string }) {
  const a = art[id] ?? art.education;
  return (
    <div
      role="img"
      aria-label={`${a.label} project photo placeholder`}
      className="relative size-full"
      style={{ background: `linear-gradient(135deg, ${a.from}, ${a.to})` }}
    >
      <span className="absolute bottom-4 right-4 font-display text-5xl text-white/25" aria-hidden>
        {a.label}
      </span>
    </div>
  );
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div role="progressbar" aria-label={label} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} className="h-[9px] bg-line">
      <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Eyebrow({ children, dark = false }: { children: React.ReactNode; dark?: boolean }) {
  return (
    <div className="mb-3">
      <p className={`eyebrow ${dark ? "!text-brand-tint" : ""}`}>{children}</p>
    </div>
  );
}

/** Krowd stat box: white square, big violet number, small label */
export function StatBox({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col justify-center bg-white p-5 text-center shadow-[0_0_30px_rgba(0,0,0,0.05)]">
      <div className="tabular text-2xl font-bold text-brand">{value}</div>
      <div className="text-sm">{label}</div>
    </div>
  );
}

/** Empty state: says what happened and offers a next step */
export function EmptyState({ title, body, action }: { title: string; body: string; action?: { href: string; label: string } }) {
  return (
    <div className="border border-dashed border-line bg-white p-10 text-center">
      <p className="font-display text-2xl text-ink">{title}</p>
      <p className="mt-2">{body}</p>
      {action && (
        <Link href={action.href} className="btn mt-6">
          {action.label}
        </Link>
      )}
    </div>
  );
}
