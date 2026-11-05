"use client";

import { useState } from "react";
import type { DonorBoardRow } from "@/lib/api";
import { Avatar } from "./Avatar";
import { Podium, RankBadge, type PodiumEntry } from "./Podium";

type Ladder = {
  id: string;
  label: string;
  short: string;
  help: string;
  value: (r: DonorBoardRow) => number;
  show: (r: DonorBoardRow, money: (c: number) => string) => string;
  unit: string;
};

// Several ladders over the same donors, like a game's rankings (kills, K/D, wins...).
const LADDERS: Ladder[] = [
  { id: "impact", label: "Impact points", short: "Impact", help: "What you gave plus the matching it unlocked, with a bonus for every extra project you reached.", value: (r) => r.impactPoints, show: (r) => `${r.impactPoints.toLocaleString()} pts`, unit: "impact points" },
  { id: "given", label: "Top givers", short: "Given", help: "Most money given this round, across every project.", value: (r) => r.given, show: (r, m) => m(r.given), unit: "given" },
  { id: "match", label: "Matching unlocked", short: "Matching", help: "Who brought in the most money from the matching pool: many people backing the same projects beats one big gift.", value: (r) => r.matchUnlocked, show: (r, m) => m(r.matchUnlocked), unit: "matching unlocked" },
  { id: "multiplier", label: "Best multiplier", short: "×", help: "Matching unlocked per $1 given: small gifts in the right places score highest.", value: (r) => r.multiplier, show: (r) => `×${r.multiplier.toFixed(2)}`, unit: "per $1" },
  { id: "reach", label: "Widest reach", short: "Reach", help: "Most projects reached, then most categories: little gifts spread wide make the pool stronger.", value: (r) => r.projectsBacked * 100 + r.categoriesReached, show: (r) => `${r.projectsBacked} projects`, unit: "projects reached" },
  { id: "agent", label: "Giving Agent", short: "Agent", help: "Most money distributed by the donor's Giving Agent within their rules.", value: (r) => r.agentGiven, show: (r, m) => m(r.agentGiven), unit: "given by their agent" },
];

const nameOf = (r: DonorBoardRow) => r.displayName ?? (r.isMe ? "You" : r.alias);

export function DonorBoard({ rows, currency, wallpaper }: { rows: DonorBoardRow[]; currency: string; wallpaper: string }) {
  const [ladderId, setLadderId] = useState("impact");
  const [scope, setScope] = useState<"all" | "named">("all");
  const ladder = LADDERS.find((l) => l.id === ladderId)!;
  const money = (c: number) => new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(c / 100);

  const pool = rows.filter((r) => (scope === "named" ? r.displayName || r.isMe : true)).filter((r) => ladder.value(r) > 0);
  // Ties share a rank (1, 1, 3...); within a tie the bigger giver is listed first
  const sorted = [...pool].sort((a, b) => ladder.value(b) - ladder.value(a) || b.given - a.given);
  const ranked = sorted.map((r) => ({ r, rank: 1 + sorted.filter((x) => ladder.value(x) > ladder.value(r)).length }));
  const me = ranked.find((x) => x.r.isMe);
  // Podium places are positions 1-3; the badge on each shows the (possibly shared) rank
  const entries: PodiumEntry[] = ranked.slice(0, 3).map(({ r, rank }, i) => ({
    key: r.alias,
    rank: i + 1,
    badge: rank,
    title: nameOf(r),
    value: ladder.show(r, money),
    label: ladder.unit,
    avatar: { name: r.displayName ?? undefined, seed: r.alias, anonymous: !r.displayName },
    you: r.isMe,
  }));

  return (
    <div className="space-y-6">
      {/* Ladder picker */}
      <div role="tablist" aria-label="Donor rankings" className="flex flex-wrap gap-2">
        {LADDERS.map((l) => (
          <button
            key={l.id}
            role="tab"
            aria-selected={l.id === ladderId}
            onClick={() => setLadderId(l.id)}
            className={`corner min-h-11 px-4 text-sm font-bold transition-colors ${l.id === ladderId ? "bg-ink text-white" : "bg-white text-ink ring-1 ring-line hover:ring-primary"}`}
            style={{ ["--corner-size" as string]: l.id === ladderId ? "8px" : "0px" }}
          >
            {l.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm">
          {ladder.help}
          {ranked.length > 3 && ranked[3].rank <= 3 && " Several donors are tied at the top."}
        </p>
        <div className="flex bg-white p-1 ring-1 ring-line text-sm" role="group" aria-label="Who to show">
          {(
            [
              ["all", "Everyone"],
              ["named", "Named donors + you"],
            ] as const
          ).map(([id, label]) => (
            <button key={id} type="button" aria-pressed={scope === id} onClick={() => setScope(id)} className={`min-h-9 px-3 font-medium ${scope === id ? "bg-primary text-white" : "text-ink"}`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {ranked.length === 0 ? (
        <p className="border border-dashed border-line bg-white p-8 text-center">No donors on this ladder yet this round.</p>
      ) : (
        <>
          <Podium entries={entries} wallpaper={wallpaper} title={`${ladder.label}: top three`} animKey={`${ladderId}-${scope}`} />

          {me && me.rank > 3 && (
            <p className="flex items-center gap-3 border-l-4 border-accent bg-ink p-4 text-white">
              <span className="bg-white">
                <RankBadge rank={me.rank} />
              </span>{" "}
              You&apos;re <strong>#{me.rank}</strong> on {ladder.label.toLowerCase()} with {ladder.show(me.r, money)}.
            </p>
          )}

          <ol className="divide-y divide-line bg-white ring-1 ring-line">
            {ranked.map(({ r, rank }) => (
              <li key={r.alias} className={`flex items-center gap-4 px-4 py-3 ${r.isMe ? "bg-accent/40" : ""}`}>
                <RankBadge rank={rank} />
                <Avatar name={r.displayName ?? undefined} seed={r.alias} anonymous={!r.displayName} size={40} label="" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-ink">
                    {nameOf(r)}
                    {r.isMe && <span className="ml-2 bg-ink px-1.5 text-[10px] font-bold uppercase tracking-wider text-white">You</span>}
                  </p>
                  <p className="text-xs">
                    {money(r.given)} given · {r.projectsBacked} {r.projectsBacked === 1 ? "project" : "projects"} · {r.categoriesReached} {r.categoriesReached === 1 ? "cause" : "causes"} · ×{r.multiplier.toFixed(2)}
                  </p>
                </div>
                <span className="tabular text-right font-display text-xl text-primary">{ladder.show(r, money)}</span>
              </li>
            ))}
          </ol>
        </>
      )}
      <p className="text-sm">Donors are anonymous unless they turn their name on in My Impact. Rankings use this round&apos;s captured gifts only.</p>
    </div>
  );
}
