import "server-only";
import { formatDate, formatMoney, getImpactUpdates, getLeaderboard, getProject, getProjects, mapLimit } from "./api";
import type { Money, Project } from "./types";

// Impact hub: articles drafted automatically from verified platform data only (released
// milestones with checked evidence, project details, the matching round). Every number comes
// from the API; nothing is invented. When Person 3's research reports exist, their text and
// photos can be added to `research` for each project and the drafts will quote them.
export type Article = {
  slug: string;
  kind: "release" | "round" | "spotlight";
  title: string;
  dek: string;
  body: string[];
  date: string;
  project?: Project;
  amount?: Money;
  evidence: number;
};

const kindLabel = { release: "Money released", round: "Matching round", spotlight: "Needs backers" } as const;
export const KIND_LABEL = kindLabel;

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export async function getImpactHub() {
  const [projects, updates, lb] = await Promise.all([getProjects(), getImpactUpdates(), getLeaderboard()]);
  const backed = projects.filter((p) => p.backerCount > 0);
  const detailed = (await mapLimit(backed, 8, (p) => getProject(p.id).catch(() => undefined))).filter((p): p is Project => Boolean(p));
  const released = detailed.flatMap((p) => (p.milestones ?? []).filter((m) => m.status === "released").map((m) => ({ p, m })));
  const currency = projects[0]?.goal.currency ?? "USD";
  const money = (a: number) => formatMoney({ amount: a, currency });

  const articles: Article[] = [];

  // 1. One article per released milestone
  for (const u of updates) {
    const p = detailed.find((x) => x.id === u.projectId) ?? projects.find((x) => x.id === u.projectId);
    if (!p) continue;
    // Repeat exactly what the release says was checked
    const both = /receipts and photos/i.test(u.caption);
    const checked = both ? "receipts and photos" : "evidence";
    const m = released.find((r) => r.p.id === p.id && r.m.title === u.title)?.m;
    const amount = m?.amount;
    const next = detailed.find((d) => d.id === p.id)?.milestones?.filter((x) => x.status !== "released").sort((a, b) => a.seq - b.seq)[0];
    articles.push({
      slug: `release-${u.id}`,
      kind: "release",
      title: `${p.title}: “${u.title}” is paid for`,
      dek: `${amount ? formatMoney(amount) : "A tranche"} went to ${p.title} in ${p.facets.region} after its ${checked} passed the checks.`,
      body: [
        `${p.title} is a ${p.facets.cause.toLowerCase()} project for ${p.facets.group.toLowerCase()} in ${p.facets.region}.${p.summary ? ` ${p.summary}` : ""}`,
        `Its step “${u.title}” has now been released${amount ? `: ${formatMoney(amount)}` : ""}. Money on this platform is never paid in one go: each step needs receipts and photos, and the checks must pass before PayPal sends the tranche.`,
        `So far ${p.backerCount} ${p.backerCount === 1 ? "person has" : "people have"} backed it, raising ${formatMoney(p.raised)} of its ${formatMoney(p.goal)} goal.`,
        next ? `Next up is “${next.title}”${next.dueDate ? `, due ${formatDate(next.dueDate)}` : ""}. This round's matching is added to that step.` : "Every step of the plan is now complete.",
      ],
      date: u.date,
      project: p,
      amount,
      evidence: both ? 2 : 1,
    });
  }

  // 2. The matching round so far
  if (lb.rows.length) {
    const top = [...lb.rows].sort((a, b) => a.rank - b.rank).slice(0, 3);
    const matched = lb.rows.reduce((s, r) => s + r.match.amount, 0);
    const backers = lb.rows.reduce((s, r) => s + r.backerCount, 0);
    articles.push({
      slug: "round-now",
      kind: "round",
      title: `${lb.roundName}: ${money(matched)} of matching is heading to ${lb.rows.filter((r) => r.match.amount > 0).length} projects`,
      dek: `${backers} backers so far. The pool follows how many people back a project, not how much one person gives.`,
      body: [
        `The ${lb.roundName} has a ${formatMoney(lb.pool)} matching pool from sponsors. ${lb.isFinal ? "The round has closed and these numbers are final." : "Until the round closes these numbers are projections, recalculated every five minutes."}`,
        `In the lead: ${top.map((r) => `${r.title} (${formatMoney(r.match)} from ${r.backerCount} backers)`).join(", ")}.`,
        `${lb.rows.filter((r) => r.capped).length} projects have reached their cap, so the rest of their share goes to the others. Each project's match is paid with its next milestone, only after that milestone's evidence passes the checks.`,
      ],
      date: lb.computedAt,
      evidence: 0,
    });
  }

  // 3. Spotlights: urgent projects nobody has backed yet
  for (const p of projects.filter((x) => x.backerCount === 0 && x.status !== "completed").sort((a, b) => b.urgency - a.urgency).slice(0, 3)) {
    articles.push({
      slug: `spotlight-${p.id}`,
      kind: "spotlight",
      title: `Be the first to back ${p.title}`,
      dek: `${cap(p.facets.cause)} for ${p.facets.group.toLowerCase()} in ${p.facets.region}: no backers yet, so the first gifts count the most in matching.`,
      body: [
        p.summary || `${cap(p.facets.cause)} for ${p.facets.group.toLowerCase()} in ${p.facets.region}.`,
        `It needs ${formatMoney(p.goal)} and has ${formatMoney(p.raised)} so far. Because matching rewards the number of backers, the first few people to back a project move its share of the pool the most.`,
        `The project was verified before listing, and its money will be released step by step against receipts and photos.`,
      ],
      date: new Date().toISOString(),
      project: p,
      evidence: 0,
    });
  }

  articles.sort((a, b) => (a.kind === "release" ? 0 : 1) - (b.kind === "release" ? 0 : 1) || b.date.localeCompare(a.date));

  const places = new Map<string, number>();
  for (const p of backed) places.set(p.facets.region, (places.get(p.facets.region) ?? 0) + p.raised.amount);

  return {
    articles,
    stats: {
      released: released.reduce((s, r) => s + r.m.amount.amount, 0),
      raised: projects.reduce((s, p) => s + p.raised.amount, 0),
      backers: projects.reduce((s, p) => s + p.backerCount, 0),
      projects: projects.length,
      places: new Set(projects.map((p) => p.facets.region)).size,
      releasedSteps: released.length,
      currency,
    },
    places: [...places.entries()].sort((a, b) => b[1] - a[1]),
  };
}
