import { Avatar } from "./Avatar";
import Link from "next/link";
import { formatMoney } from "@/lib/api";
import type { BackerStory, Project, Sponsor } from "@/lib/types";
import { Eyebrow } from "./ui";

// Krowd testimonials, repurposed: backers' words, with the project they backed. Static cards, no slider;
// they scroll sideways on phones.
export function BackerStories({ stories, projects }: { stories: BackerStory[]; projects: Project[] }) {
  if (stories.length === 0) return null;
  return (
    <section className="bg-surface-alt pb-16 lg:pb-[120px]">
      <div className="relative bg-cobalt-green py-10 text-center">
        <h2 className="section-title">What backers are saying</h2>
        <span className="absolute left-1/2 top-full -ml-3 border-x-[12px] border-t-[12px] border-x-transparent border-t-cobalt-green" aria-hidden />
      </div>
      <div className="container-k pt-16">
        <ul className="-mx-4 flex snap-x gap-[30px] overflow-x-auto px-4 pb-12 md:grid md:grid-cols-3 md:overflow-visible">
          {stories.map((s, i) => {
            const p = projects.find((x) => x.id === s.projectId);
            return (
              <li
                key={s.id}
                className={`relative min-w-[85%] snap-center bg-white px-8 pb-16 pt-10 text-center md:min-w-0 ${
                  i === 1 ? "corner shadow-[0_15px_35px_rgba(11,46,51,0.08)] ring-2 ring-inset ring-growth" : ""
                }`}
                style={{ ["--corner-size" as string]: "29px" }}
              >
                <span className="mx-auto mb-6 grid size-[50px] place-items-center rounded-full bg-brand font-display text-3xl text-white" aria-hidden>
                  &ldquo;
                </span>
                <blockquote className="mb-6 text-lg leading-9">{s.quote}</blockquote>
                <p className="text-xl text-ink">{s.name}</p>
                <p className="text-sm">{s.role}</p>
                {p && (
                  <Link href={`/projects/${p.id}`} className="mt-2 inline-block text-sm font-medium text-brand hover:underline">
                    Backed {p.title}
                  </Link>
                )}
                <span className="absolute -bottom-[30px] left-1/2 -ml-[30px] block size-[60px] overflow-hidden border-4 border-white" aria-hidden>
                  <Avatar name={s.name} seed={s.id} size={52} />
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

// Krowd brand-logo strip, repurposed: the sponsors whose money makes up the matching pool.
export function SponsorStrip({ sponsors }: { sponsors: Sponsor[] }) {
  if (sponsors.length === 0) return null;
  const total = sponsors.reduce((s, x) => s + x.pool.amount, 0);
  return (
    <section className="border-y border-line py-12">
      <div className="container-k">
        <div className="mb-6 text-center">
          <Eyebrow>Matching pool</Eyebrow>
          <p className="text-ink">
            <span className="font-bold">{formatMoney({ amount: total, currency: sponsors[0]?.pool.currency ?? "USD" })}</span> from{" "}
            {sponsors.length} sponsors this round
          </p>
        </div>
        <ul className="grid grid-cols-2 gap-px bg-line sm:grid-cols-4">
          {sponsors.map((s) => (
            <li key={s.id} className="flex flex-col items-center justify-center bg-white p-6 text-center grayscale">
              <span className="font-display text-xl text-ink">{s.name}</span>
              <span className="tabular text-sm">{formatMoney(s.pool)}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
