import Link from "next/link";
import type { LeaderboardRow } from "@/lib/types";
import { Avatar } from "./Avatar";

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

// Top three on a podium (2nd, 1st, 3rd), on a dark doodle background, game-style.
export function Podium({ rows, wallpaper }: { rows: LeaderboardRow[]; wallpaper: string }) {
  const top = [...rows].sort((a, b) => a.rank - b.rank).slice(0, 3);
  if (top.length === 0) return null;
  const order = [top[1], top[0], top[2]].filter(Boolean);
  const heights: Record<number, string> = { 1: "h-44", 2: "h-32", 3: "h-24" };
  return (
    <section aria-label="Top three projects" className="relative overflow-hidden bg-ink px-4 pb-0 pt-10 text-white" style={{ backgroundImage: wallpaper, backgroundSize: "320px" }}>
      <h2 className="mb-8 text-center text-3xl text-white">This round&apos;s top three</h2>
      <ol className="mx-auto flex max-w-3xl items-end justify-center gap-3 sm:gap-6">
        {order.map((r) => (
          <li key={r.projectId} className="flex w-1/3 max-w-[220px] flex-col items-center text-center">
            <div className="relative">
              <span className={`block overflow-hidden ring-4 ${r.rank === 1 ? "ring-accent" : "ring-white/30"}`}>
                <Avatar name={r.title} seed={r.projectId} size={r.rank === 1 ? 96 : 72} label={r.title} />
              </span>
              {r.rank === 1 && <span className="absolute -top-7 left-1/2 -translate-x-1/2 text-3xl" aria-hidden>👑</span>}
              <span className="absolute -bottom-3 left-1/2 -translate-x-1/2">
                <RankBadge rank={r.rank} size={30} />
              </span>
            </div>
            <Link href={`/projects/${r.projectId}`} className="mt-5 line-clamp-2 font-display text-lg leading-6 text-white hover:text-accent">
              {r.title}
            </Link>
            <p className="tabular mt-1 text-sm text-cobalt-green">
              {fmt(r.match.amount, r.match.currency)} match · {r.backerCount} backers
            </p>
            <div className={`mt-4 w-full ${heights[r.rank]} grid place-items-start justify-center bg-primary pt-3 font-display text-4xl text-white/80`} style={{ background: r.rank === 1 ? "linear-gradient(#00978D,#007190)" : undefined }}>
              {r.rank}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
