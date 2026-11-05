import Link from "next/link";
import { getGlobePins } from "@/lib/globe";

import { Countdown } from "@/components/Countdown";
import { Podium, projectPodium } from "@/components/Podium";
import { doodleTile, doodleUrl } from "@/lib/doodles";
import { LeaderboardGrid } from "@/components/LeaderboardGrid";
import { PageTitle } from "@/components/PageTitle";
import { EmptyState, Eyebrow, StatBox } from "@/components/ui";
import { formatMoney, getDonorBoard, getLeaderboard } from "@/lib/api";
import { DonorBoard } from "@/components/DonorBoard";

// Rebuilt in the background at most every 30 s, so tab switches serve a ready page.
export const revalidate = 60;

const WALLPAPER = doodleUrl(doodleTile({ stroke: "#1d4248", seed: 31, density: 7 }));

export default async function LeaderboardPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab: rawTab } = await searchParams;
  const tab = rawTab === "projects" ? "projects" : "donors";
  const [lb, globe] = await Promise.all([getLeaderboard(), getGlobePins()]);
  const donors = await getDonorBoard(lb.roundId);
  const matched = lb.rows.reduce((s, r) => s + r.match.amount, 0);
  const backers = lb.rows.reduce((s, r) => s + r.backerCount, 0);
  const days = Math.max(0, Math.ceil((new Date(lb.endsAt).getTime() - Date.now()) / 86_400_000));
  const updated = new Date(lb.computedAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

  return (
    <>
      <PageTitle title="Leaderboard" crumb="Leaderboard" globe={globe} />
      <section className="section">
        <div className="container-k space-y-10">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div className="max-w-[640px]">
              <Eyebrow>{lb.roundName}</Eyebrow>
              <h2 className="section-title mb-4">{tab === "donors" ? "Who gives, and who unlocks the most" : "Where the matching pool goes"}</h2>
              <p className="text-lg leading-8">
                The pool is shared by how many people back each project, not how much one person gives. Caps stop any
                single project taking everything.
              </p>
            </div>
            <div className="text-right" aria-live="polite">
              <span className={`inline-block px-3 text-xs font-bold uppercase leading-7 tracking-[2px] ${lb.isFinal ? "bg-ink text-white" : "bg-cobalt-green text-ink"}`}>
                {lb.isFinal ? "Final results" : "Projected"}
              </span>
              <p className="mt-2 text-sm">
                {lb.isFinal ? "Round closed." : "Recalculated every 5 minutes."} Updated {updated}.
              </p>
              {!lb.isFinal && (
                <div className="mt-4 flex justify-end">
                  <Countdown small endsAt={lb.endsAt} label="Round closes in" />
                </div>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatBox value={formatMoney(lb.pool)} label="Matching pool" />
            <StatBox value={formatMoney({ amount: matched, currency: lb.pool.currency })} label={lb.isFinal ? "Matched" : "Projected match"} />
            <StatBox value={String(backers)} label="Backers" />
            <StatBox value={lb.isFinal ? "Closed" : String(days)} label={lb.isFinal ? "Round" : "Days left"} />
          </div>

          {lb.sample && (
            <p className="border-l-4 border-accent bg-white p-3 text-sm text-ink">
              Sample numbers. Connect the core API (<code>NEXT_PUBLIC_API_URL</code>) to see the real matching engine.
            </p>
          )}

          <nav aria-label="Leaderboards" className="flex w-fit gap-1 bg-white p-1 shadow-[0_0_30px_rgba(0,0,0,0.05)]">
            {(
              [
                ["donors", "Donors", "/leaderboard"],
                ["projects", "Projects", "/leaderboard?tab=projects"],
              ] as const
            ).map(([id, label, href]) => (
              <Link key={id} href={href} aria-current={tab === id ? "page" : undefined} className={`flex min-h-12 items-center px-6 text-lg font-medium ${tab === id ? "bg-ink text-white" : "text-ink hover:bg-surface-alt"}`}>
                {label}
              </Link>
            ))}
          </nav>

          {tab === "donors" ? (
            <DonorBoard rows={donors.rows} currency={donors.currency} wallpaper={WALLPAPER} />
          ) : (
            <>
          {lb.rows.length > 0 && <Podium entries={projectPodium(lb.rows)} wallpaper={WALLPAPER} title="This round's top three projects" />}

          {lb.rows.length === 0 ? (
            <EmptyState
              title="No backers yet this round"
              body="The leaderboard fills in as soon as the first donations arrive."
              action={{ href: "/projects", label: "Back a project" }}
            />
          ) : (
            <LeaderboardGrid rows={lb.rows} refreshSeconds={lb.isFinal ? undefined : 60} />
          )}
            </>
          )}

          <p className="text-sm">
            Want your name on the public leaderboard? It&apos;s off by default.{" "}
            <Link href="/report" className="font-medium text-brand underline">
              Change it in My Impact
            </Link>
            .
          </p>
        </div>
      </section>
    </>
  );
}
