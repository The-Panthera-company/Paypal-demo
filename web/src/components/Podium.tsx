import Link from "next/link";
import type { LeaderboardRow } from "@/lib/types";
import { Avatar } from "./Avatar";
import { RollingNumber } from "./RollingNumber";

const fmt = (c: number, cur: string) => new Intl.NumberFormat(undefined, { style: "currency", currency: cur, maximumFractionDigits: 0 }).format(c / 100);
const MEDAL = ["#FFEFAE", "#D9E8DF", "#C9A27A"]; // gold (lemon), silver (mint grey), bronze

/** Rank badge: medals for 1-3, a numbered square for the rest */
export function RankBadge({ rank, size = 32 }: { rank: number; size?: number }) {
  const m = MEDAL[rank - 1];
  return (
    <span
      className="tabular inline-grid shrink-0 place-items-center font-bold leading-none text-ink"
      style={{ width: size, height: size, background: m ?? "transparent", border: m ? "none" : "2px solid var(--color-line)", fontSize: size * 0.5, clipPath: m ? "polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%)" : undefined }}
      aria-label={`Rank ${rank}`}
    >
      {rank}
    </span>
  );
}

export type PodiumEntry = {
  key: string;
  rank: number;
  /** rank shown on the badge when it differs from the podium place (ties) */
  badge?: number;
  title: string;
  href?: string;
  /** big figure on the plaque, e.g. "$4,000" */
  value: string;
  /** small line under it, e.g. "matching unlocked" */
  label: string;
  avatar: { name?: string; seed: string; anonymous?: boolean };
  you?: boolean;
};

// Top three on a podium (2nd, 1st, 3rd) on a dark doodle background. When it appears the steps
// rise one after another (3rd, 2nd, 1st), then the winners and their plaques drop in. Plaques are
// styled like the site's buttons (lemon block with the dark corner square). `animKey` replays it.
export function Podium({ entries, wallpaper, title, animKey = "" }: { entries: PodiumEntry[]; wallpaper: string; title: string; animKey?: string }) {
  const top = [...entries].sort((a, b) => a.rank - b.rank).slice(0, 3);
  if (top.length === 0) return null;
  const order = [top[1], top[0], top[2]].filter(Boolean);
  const height: Record<number, number> = { 1: 176, 2: 128, 3: 96 };
  const delay: Record<number, number> = { 3: 0, 2: 250, 1: 500 };
  return (
    <section aria-label={title} className="relative overflow-hidden bg-ink px-4 pt-10 text-white" style={{ backgroundImage: wallpaper, backgroundSize: "320px" }}>
      <h2 className="mb-10 text-center text-3xl text-white">{title}</h2>
      <ol key={animKey} className="mx-auto flex max-w-3xl items-end justify-center gap-3 sm:gap-6">
        {order.map((r) => (
          <li key={r.key} className="flex w-1/3 max-w-[230px] flex-col items-center text-center">
            <div className="flex flex-col items-center opacity-0 animate-[podium-up_.7s_cubic-bezier(.2,.9,.3,1.1)_forwards]" style={{ animationDelay: `${delay[r.rank] + 700}ms` }}>
              <div className="relative">
                <span className={`block overflow-hidden ring-4 ${r.rank === 1 ? "ring-accent" : "ring-white/30"}`}>
                  <Avatar name={r.avatar.name} seed={r.avatar.seed} anonymous={r.avatar.anonymous} size={r.rank === 1 ? 96 : 72} label={r.title} />
                </span>
                {r.rank === 1 && <span className="absolute -top-8 left-1/2 -translate-x-1/2 text-3xl" aria-hidden>👑</span>}
                <span className="absolute -bottom-3 left-1/2 -translate-x-1/2">
                  <RankBadge rank={r.badge ?? r.rank} size={30} />
                </span>
              </div>
              {r.href ? (
                <Link href={r.href} className="mt-5 line-clamp-2 font-display text-lg leading-6 text-white hover:text-accent">
                  {r.title}
                </Link>
              ) : (
                <p className="mt-5 line-clamp-2 font-display text-lg leading-6 text-white">
                  {r.title}
                  {r.you && <span className="ml-1 bg-accent px-1.5 align-middle font-sans text-[10px] font-bold uppercase tracking-wider text-ink">You</span>}
                </p>
              )}
              {/* Plaque, button-style */}
              <p className={`corner relative mt-3 px-4 py-2 ${r.rank === 1 ? "bg-accent text-ink" : "bg-white/10 text-white ring-1 ring-white/25"}`} style={{ ["--corner-size" as string]: "10px" }}>
                <span className="block font-display text-2xl leading-7"><RollingNumber value={r.value} delay={delay[r.rank] + 900} /></span>
                <span className={`block text-[11px] font-bold uppercase tracking-[2px] ${r.rank === 1 ? "text-ink/70" : "text-cobalt-green"}`}>{r.label}</span>
              </p>
            </div>
            {/* The step rises */}
            <div className="relative mt-4 w-full overflow-hidden" style={{ height: height[r.rank] }}>
              <div
                className="absolute inset-x-0 bottom-0 grid h-full origin-bottom place-items-start justify-center pt-3 font-display text-4xl text-white/85 animate-[podium-rise_.8s_cubic-bezier(.2,.9,.3,1.15)_both]"
                style={{ animationDelay: `${delay[r.rank]}ms`, background: r.rank === 1 ? "linear-gradient(#00978D,#007190)" : "#007190" }}
              >
                {r.rank}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** The project leaderboard's rows as podium entries */
export function projectPodium(rows: LeaderboardRow[]): PodiumEntry[] {
  return rows.map((r) => ({
    key: r.projectId,
    rank: r.rank,
    title: r.title,
    href: `/projects/${r.projectId}`,
    value: fmt(r.match.amount, r.match.currency),
    label: `match · ${r.backerCount} backers`,
    avatar: { name: r.title, seed: r.projectId },
  }));
}
