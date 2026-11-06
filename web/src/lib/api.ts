import { unstable_noStore as noStore } from "next/cache";
// One place for every call to the core API (Person 1, api/openapi.json).
// With NEXT_PUBLIC_API_URL unset, the app uses local mock data. Set it to the API URL
// (http://localhost:8000 locally, the Render URL when deployed) and the adapters below
// turn the API's snake_case / *_cents fields into the shapes in ./types, so pages never change.
import { cache } from "react";
import { backerStories, categories, impactUpdates, projects, sponsors } from "./mock-data";
import type { BackerStory, Category, DonorReport, ImpactUpdate, Leaderboard, LeaderboardRow, Money, Project, ProjectFilters, Sponsor } from "./types";

// In Docker the website's server reaches the API by its service name (API_INTERNAL_URL, e.g. http://api:8000),
// while the browser uses the public address (NEXT_PUBLIC_API_URL). Elsewhere both are the same.
const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const API_URL = (typeof window === "undefined" ? process.env.API_INTERNAL_URL : undefined)?.replace(/\/$/, "") || PUBLIC_API_URL;

/** Catalogue reads are shared for `revalidate` seconds (projects change rarely; the matching projection
 *  every 5 minutes), so a page view usually needs no API call at all. Admin and donor data use no-store. */
/** Thrown for a 4xx answer, so callers can tell "not there" from "server down" */
export class ApiError extends Error {
  constructor(public status: number, path: string) {
    super(`GET ${path} failed: ${status}`);
  }
}

/**
 * GET with a time limit and one retry. Render's free API sleeps after 15 minutes idle and the
 * first request while it wakes can fail; one retry 2 s later usually lands.
 */
const BUILDING = process.env.NEXT_PHASE === "phase-production-build";

/**
 * During `next build` a page is pre-rendered once. If the API is slow or asleep (Render), a failed
 * call would fail the whole deploy. Instead the page opts out of pre-rendering (noStore marks it
 * dynamic) and is rendered on the first visit. Outside the build this does nothing.
 */
function bailOutOfBuild() {
  if (BUILDING) noStore();
}

async function get<T>(path: string, revalidate = 30): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(`${API_URL}${path}`, { next: { revalidate }, signal: AbortSignal.timeout(BUILDING ? 10_000 : 25_000) });
      if (res.status >= 400 && res.status < 500) throw new ApiError(res.status, path);
      if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
      return (await res.json()) as T;
    } catch (e) {
      if (e instanceof ApiError || attempt >= 1) {
        bailOutOfBuild();
        throw e;
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

/** Like get(), but routes Person 1 hasn't built yet (X-Stub header = example data) count as empty */
async function getBuilt<T>(path: string, empty: T): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { next: { revalidate: 30 } }).catch((e) => {
    bailOutOfBuild();
    throw e;
  });
  if (!res.ok || res.headers.has("x-stub")) return empty;
  return res.json() as Promise<T>;
}

// ---- API shapes (subset of api/openapi.json) ----
type ApiCategory = { id: number; name: string; project_count: number };
type ApiProject = {
  id: number;
  title: string;
  category_id: number;
  category: string;
  tags: string[];
  cause: string | null;
  beneficiary_group: string | null;
  region: string | null;
  urgency: number;
  status: string;
  goal_cents: number;
  raised_cents: number;
  backer_count: number;
  currency: string;
  summary?: string;
  facilitator?: string;
  verified_at?: string | null;
  projected_match_cents?: number;
  matching_frozen?: boolean;
  milestones?: { id: number; seq: number; title: string; amount_cents: number; match_amount_cents: number; currency: string; due_date: string | null; status: string }[];
};
type ApiRound = { id: number; name: string; ends_at: string; matching_pool_cents: number; currency: string };
type ApiLeaderboard = {
  round_id: number;
  is_final: boolean;
  computed_at: string;
  currency: string;
  rows: {
    rank: number;
    project_id: number;
    title: string;
    category: string;
    backer_count: number;
    raised_cents: number;
    score: number;
    floor_cents: number;
    crowd_cents: number;
    match_cents: number;
    capped: boolean;
    matching_frozen: boolean;
  }[];
};
type ApiStory = { id: number; project_id: number; title: string; body: string; evidence_urls: string[]; created_at: string };

/** The site uses the category name as its id ("health"), the API a number */
const slug = (name: string) => name.trim().toLowerCase();
const money = (cents: number, currency: string) => ({ amount: cents, currency });
/** The API stores facet values in lowercase ("literacy"); show "Literacy" */
const label = (v: string | null, fallback: string) => (v ? v.charAt(0).toUpperCase() + v.slice(1) : fallback);

const currentRoundEnd = cache(() =>
  get<ApiRound>("/rounds/current")
    .then((r) => r.ends_at)
    .catch(() => new Date(Date.now() + 30 * 86_400_000).toISOString()),
);

function toProject(p: ApiProject, endsAt: string): Project {
  return {
    id: String(p.id),
    title: p.title,
    categoryId: slug(p.category),
    facilitator: p.facilitator ?? "",
    summary: p.summary ?? "",
    facets: { cause: label(p.cause, "Other"), group: label(p.beneficiary_group, "Everyone"), region: label(p.region, "Global") },
    tags: p.tags,
    goal: money(p.goal_cents, p.currency),
    raised: money(p.raised_cents, p.currency),
    backerCount: p.backer_count,
    urgency: Math.min(5, Math.max(1, p.urgency)) as Project["urgency"],
    status: (["verified", "active", "frozen", "completed"].includes(p.status) ? p.status : "active") as Project["status"],
    endsAt,
    verifiedAt: p.verified_at ?? undefined,
    projectedMatch: p.projected_match_cents !== undefined ? money(p.projected_match_cents, p.currency) : undefined,
    matchingFrozen: p.matching_frozen ?? false,
    milestones: p.milestones?.map((m) => ({
      id: String(m.id),
      seq: m.seq,
      title: m.title,
      amount: money(m.amount_cents, m.currency),
      match: money(m.match_amount_cents, m.currency),
      dueDate: m.due_date,
      status: (["open", "evidence_submitted", "released", "held"].includes(m.status) ? m.status : "open") as "open",
    })),
  };
}

// cache(): within one page view, repeated calls share one answer
const apiCategories = cache((): Promise<ApiCategory[]> => get<ApiCategory[]>("/categories"));
const apiProjects = cache((query: string): Promise<ApiProject[]> => get<ApiProject[]>(`/projects?${query}`));

// ---- Public functions used by the pages ----

export async function getCategories(): Promise<Category[]> {
  if (!API_URL) return categories;
  const [cats, all] = await Promise.all([apiCategories(), getProjects()]);
  return cats.map((c) => {
    const mine = all.filter((p) => p.categoryId === slug(c.name));
    return {
      id: slug(c.name),
      apiId: c.id,
      name: c.name,
      projectCount: c.project_count,
      raised: money(mine.reduce((s, p) => s + p.raised.amount, 0), mine[0]?.raised.currency ?? "USD"),
    };
  });
}

export async function getProjects(filters: ProjectFilters = {}): Promise<Project[]> {
  if (API_URL) {
    const params = new URLSearchParams();
    if (filters.category) {
      const cat = (await apiCategories()).find((c) => slug(c.name) === filters.category);
      if (cat) params.set("category_id", String(cat.id));
    }
    if (filters.cause) params.set("cause", filters.cause.toLowerCase());
    if (filters.group) params.set("beneficiary_group", filters.group.toLowerCase());
    if (filters.region) params.set("region", filters.region);
    if (filters.q) params.set("q", filters.q);
    params.set("limit", "200"); // the API's default is 50; 200 is its maximum
    const [rows, endsAt] = await Promise.all([apiProjects(params.toString()), currentRoundEnd()]);
    return rows.map((p) => toProject(p, endsAt));
  }
  const q = filters.q?.toLowerCase();
  return projects.filter(
    (p) =>
      (!filters.category || p.categoryId === filters.category) &&
      (!filters.cause || p.facets.cause === filters.cause) &&
      (!filters.group || p.facets.group === filters.group) &&
      (!filters.region || p.facets.region === filters.region) &&
      (!q || p.title.toLowerCase().includes(q) || p.summary.toLowerCase().includes(q)),
  );
}

export async function getProject(id: string): Promise<Project | undefined> {
  if (!API_URL) return projects.find((p) => p.id === id);
  const res = await fetch(`${API_URL}/projects/${id}`, { next: { revalidate: 30 } });
  if (res.status === 404) return undefined;
  if (!res.ok) throw new Error(`GET /projects/${id} failed: ${res.status}`);
  return toProject((await res.json()) as ApiProject, await currentRoundEnd());
}

export function formatMoney({ amount, currency }: { amount: number; currency: string }) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(
    amount / 100,
  );
}

/** Distinct facet values, for the filter dropdowns */
export async function getFacetOptions() {
  const all = await getProjects();
  const uniq = (key: keyof Project["facets"]) => [...new Set(all.map((p) => p.facets[key]))].sort();
  return { cause: uniq("cause"), group: uniq("group"), region: uniq("region") };
}

export function daysLeft(p: Project) {
  return Math.max(0, Math.ceil((new Date(p.endsAt).getTime() - Date.now()) / 86_400_000));
}

/** Milestone evidence. The API calls these "stories" (written when a tranche is released). */
export async function getImpactUpdates(projectId?: string): Promise<ImpactUpdate[]> {
  if (!API_URL) return impactUpdates.filter((u) => !projectId || u.projectId === projectId);
  // Only projects with backers can have released a milestone, so skip the rest (one call per project)
  const ids = projectId ? [projectId] : (await getProjects()).filter((p) => p.backerCount > 0).map((p) => p.id);
  const lists = await Promise.all(
    ids.map((id) => getBuilt<ApiStory[]>(`/projects/${id}/stories`, []).catch(() => [] as ApiStory[])),
  );
  return lists
    .flat()
    .map((s) => ({
      id: String(s.id),
      projectId: String(s.project_id),
      title: s.title,
      caption: s.body,
      kind: /receipt/i.test(s.title + s.body) ? ("receipt" as const) : ("photo" as const),
      date: s.created_at,
    }))
    .sort((a, b) => b.date.localeCompare(a.date));
}

/** Not in the API yet: sections hide themselves when these are empty. */
export async function getBackerStories(): Promise<BackerStory[]> {
  return API_URL ? [] : backerStories;
}

/** Sponsors who added to the open round's pool (GET /rounds/{id}/sponsors), largest first */
export async function getSponsors(): Promise<Sponsor[]> {
  if (!API_URL) return sponsors;
  try {
    const round = await get<ApiRound>("/rounds/current");
    const d = await get<{ currency: string; sponsors: { name: string | null; amount_cents: number; given_at: string }[] }>(`/rounds/${round.id}/sponsors`, 60);
    return d.sponsors.map((x, i) => ({ id: `${i}-${x.given_at}`, name: x.name || "Anonymous sponsor", pool: money(x.amount_cents, d.currency) }));
  } catch {
    return [];
  }
}

export async function getSimilarProjects(p: Project, limit = 3): Promise<Project[]> {
  const all = await getProjects({ category: p.categoryId });
  return all.filter((x) => x.id !== p.id).slice(0, limit);
}

export function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** Matching leaderboard for the current round: projected while open, final after close. */
export async function getLeaderboard(): Promise<Leaderboard> {
  if (!API_URL) return sampleLeaderboard();
  let round: ApiRound;
  try {
    round = await get<ApiRound>("/rounds/current");
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 404)) throw e;
    // No matching round open yet: an empty board, not an error page
    return { roundId: "", roundName: "No round open yet", endsAt: new Date().toISOString(), pool: money(0, "USD"), isFinal: false, computedAt: new Date().toISOString(), rows: [], sample: false };
  }
  const lb = await get<ApiLeaderboard>(`/rounds/${round.id}/leaderboard`, 60);
  const c = lb.currency;
  return {
    roundId: String(round.id),
    roundName: round.name,
    endsAt: round.ends_at,
    pool: money(round.matching_pool_cents, round.currency),
    isFinal: lb.is_final,
    computedAt: lb.computed_at,
    sample: false,
    rows: lb.rows.map((r) => ({
      rank: r.rank,
      projectId: String(r.project_id),
      title: r.title,
      categoryId: slug(r.category),
      backerCount: r.backer_count,
      raised: money(r.raised_cents, c),
      score: r.score,
      floor: money(r.floor_cents, c),
      crowd: money(r.crowd_cents, c),
      match: money(r.match_cents, c),
      capped: r.capped,
      frozen: r.matching_frozen,
    })),
  };
}

/** Rough two-level quadratic funding over the sample projects (equal gifts per backer),
 *  only so the page has something to show without the API. The real numbers come from Person 1's engine. */
function sampleLeaderboard(): Leaderboard {
  const pool = 10_000_00;
  const scoreOf = (p: Project) => {
    if (p.backerCount === 0) return 0;
    const d = p.raised.amount / p.backerCount;
    return p.backerCount * p.backerCount * d - p.backerCount * d;
  };
  const cats = [...new Set(projects.map((p) => p.categoryId))];
  const catScore = Object.fromEntries(cats.map((c) => [c, projects.filter((p) => p.categoryId === c).reduce((s, p) => s + scoreOf(p), 0)]));
  const totalCat = Object.values(catScore).reduce((a, b) => a + b, 0) || 1;
  const rows: LeaderboardRow[] = [];
  for (const c of cats) {
    const mine = projects.filter((p) => p.categoryId === c);
    const catPool = Math.round((pool * catScore[c]) / totalCat);
    const floorEach = Math.round((catPool * 0.2) / mine.length);
    const total = mine.reduce((s, p) => s + scoreOf(p), 0) || 1;
    const cap = Math.round(catPool * 0.4);
    for (const p of mine) {
      const crowd = Math.round((catPool * 0.8 * scoreOf(p)) / total);
      const before = floorEach + crowd;
      rows.push({
        rank: 0,
        projectId: p.id,
        title: p.title,
        categoryId: p.categoryId,
        backerCount: p.backerCount,
        raised: p.raised,
        score: Math.round(scoreOf(p) / 100),
        floor: money(floorEach, "USD"),
        crowd: money(crowd, "USD"),
        match: money(Math.min(before, cap), "USD"),
        capped: before > cap,
        frozen: false,
      });
    }
  }
  rows.sort((a, b) => b.match.amount - a.match.amount).forEach((r, i) => (r.rank = i + 1));
  return {
    roundId: "sample",
    roundName: "Sample round",
    endsAt: projects[0]?.endsAt ?? new Date().toISOString(),
    pool: money(pool, "USD"),
    isFinal: false,
    computedAt: new Date().toISOString(),
    rows,
    sample: true,
  };
}

/** The current matching round (name and end date) for countdowns */
export async function getRound(): Promise<{ id?: number; name: string; endsAt: string; pool?: Money }> {
  if (!API_URL) return { name: "Sample round", endsAt: projects[0]?.endsAt ?? new Date(Date.now() + 7 * 86_400_000).toISOString() };
  // No round open (or API unreachable): keep the page up with a placeholder countdown
  try {
    const r = await get<ApiRound>("/rounds/current");
    return { id: r.id, name: r.name, endsAt: r.ends_at, pool: money(r.matching_pool_cents, r.currency) };
  } catch {
    return { name: "Next round", endsAt: new Date(Date.now() + 30 * 86_400_000).toISOString() };
  }
}

type ApiReport = {
  donor_id: number;
  currency: string;
  total_given_cents: number;
  match_unlocked_cents: number;
  gifts: { donation_id: number; project_id: number | null; project_title: string | null; via: "PROJECT" | "CATEGORY" | "AGENT"; amount_cents: number; status: string; match_unlocked_cents: number }[];
  updates: ApiStory[];
  agent_report: string | null;
};

/** The donor's report. Never cached: it is personal and changes with every gift. */
export async function getDonorReport(donorId: string): Promise<DonorReport | null> {
  if (!API_URL) return sampleReport();
  const [r, d] = await Promise.all([
    fetch(`${API_URL}/donors/${donorId}/report`, { cache: "no-store" }),
    fetch(`${API_URL}/donors/${donorId}`, { cache: "no-store" }),
  ]);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`GET /donors/${donorId}/report failed: ${r.status}`);
  const rep = (await r.json()) as ApiReport;
  const donor = d.ok ? ((await d.json()) as { show_on_leaderboard: boolean }) : { show_on_leaderboard: false };
  const c = rep.currency;
  return {
    donorId: String(rep.donor_id),
    totalGiven: money(rep.total_given_cents, c),
    matchUnlocked: money(rep.match_unlocked_cents, c),
    gifts: rep.gifts.map((g) => ({
      donationId: String(g.donation_id),
      projectId: g.project_id === null ? null : String(g.project_id),
      projectTitle: g.project_title,
      via: g.via,
      amount: money(g.amount_cents, c),
      matchUnlocked: money(g.match_unlocked_cents, c),
      status: g.status,
    })),
    updates: rep.updates.map((s) => ({
      id: String(s.id),
      projectId: String(s.project_id),
      title: s.title,
      caption: s.body,
      kind: /receipt/i.test(s.title + s.body) ? ("receipt" as const) : ("photo" as const),
      date: s.created_at,
    })),
    agentReport: rep.agent_report,
    showOnLeaderboard: donor.show_on_leaderboard,
    sample: false,
  };
}

function sampleReport(): DonorReport {
  const m = (a: number) => money(a, "USD");
  const gift = (id: string, p: Project, amount: number, match: number, via: "PROJECT" | "AGENT" = "PROJECT") => ({
    donationId: id, projectId: p.id, projectTitle: p.title, via, amount: m(amount), matchUnlocked: m(match), status: "captured",
  });
  const [a, b, c] = projects;
  return {
    donorId: "sample",
    totalGiven: m(4_500),
    matchUnlocked: m(11_200),
    gifts: [gift("101", a, 2_000, 5_750), gift("102", b, 1_500, 4_150), gift("103", c, 1_000, 1_300, "AGENT")],
    updates: impactUpdates.filter((u) => [a.id, b.id, c.id].includes(u.projectId)),
    agentReport: `$10 to ${c.title}: 4 backers, 13% funded, receipts uploaded. Skipped a health project: outside your chosen causes.`,
    showOnLeaderboard: false,
    sample: true,
  };
}

export type DonorBoardRow = {
  alias: string;
  displayName: string | null;
  isMe: boolean;
  given: number;
  matchUnlocked: number;
  multiplier: number;
  projectsBacked: number;
  categoriesReached: number;
  agentGiven: number;
  impactPoints: number;
};

/** Donor ladders for the round (GET /rounds/{id}/donors). Empty when there's no round or API. */
export async function getDonorBoard(roundId: string, me = process.env.NEXT_PUBLIC_DEMO_DONOR_ID ?? "1"): Promise<{ currency: string; rows: DonorBoardRow[] }> {
  if (!API_URL || !roundId) return { currency: "USD", rows: [] };
  try {
    const d = await get<{ currency: string; rows: Record<string, number | string | boolean | null>[] }>(`/rounds/${roundId}/donors?me=${me}`, 60);
    return {
      currency: d.currency,
      rows: d.rows.map((r) => ({
        alias: String(r.alias),
        displayName: (r.display_name as string | null) ?? null,
        isMe: Boolean(r.is_me),
        given: Number(r.given_cents),
        matchUnlocked: Number(r.match_unlocked_cents),
        multiplier: Number(r.multiplier),
        projectsBacked: Number(r.projects_backed),
        categoriesReached: Number(r.categories_reached),
        agentGiven: Number(r.agent_given_cents),
        impactPoints: Number(r.impact_points),
      })),
    };
  } catch {
    return { currency: "USD", rows: [] };
  }
}

export type RoundResults = {
  roundId: number;
  name: string;
  status: "scheduled" | "open" | "closing" | "closed";
  isFinal: boolean;
  currency: string;
  pool: number;
  sponsored: number;
  matched: number;
  unspent: number;
  raised: number;
  backers: number;
  rows: { projectId: string; title: string; category: string; raised: number; backers: number; projected: number; final: number | null; capped: boolean }[];
};

/** GET /rounds/{id}/results: totals and projected vs final match per project. null if unknown. */
export async function getRoundResults(roundId: string | number): Promise<RoundResults | null> {
  if (!API_URL || !roundId) return null;
  try {
    const d = await get<{
      round_id: number; name: string; status: RoundResults["status"]; is_final: boolean; currency: string;
      matching_pool_cents: number; sponsored_cents: number; matched_cents: number; unspent_cents: number; raised_cents: number; backers: number;
      rows: { project_id: number; title: string; category: string; raised_cents: number; backer_count: number; projected_match_cents: number; final_match_cents: number | null; capped: boolean }[];
    }>(`/rounds/${roundId}/results`, 60);
    return {
      roundId: d.round_id, name: d.name, status: d.status, isFinal: d.is_final, currency: d.currency,
      pool: d.matching_pool_cents, sponsored: d.sponsored_cents, matched: d.matched_cents, unspent: d.unspent_cents, raised: d.raised_cents, backers: d.backers,
      rows: d.rows.map((r) => ({ projectId: String(r.project_id), title: r.title, category: r.category, raised: r.raised_cents, backers: r.backer_count, projected: r.projected_match_cents, final: r.final_match_cents, capped: r.capped })),
    };
  } catch {
    return null;
  }
}

/** All rounds, newest first (GET /rounds) */
export async function getRounds(): Promise<{ id: number; name: string; status: string; endsAt: string }[]> {
  if (!API_URL) return [];
  try {
    return (await get<{ id: number; name: string; status: string; ends_at: string }[]>("/rounds", 60)).map((r) => ({ id: r.id, name: r.name, status: r.status, endsAt: r.ends_at }));
  } catch {
    return [];
  }
}


// Agent trace helpers live in a browser-safe module; re-exported here for one import path.
export { fetchAgentActivity, fetchAgentRun, fetchAgentRuns, type AgentActivity, type AgentRun, type TraceStep } from "./agent-trace";
