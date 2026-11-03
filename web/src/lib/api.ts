// One place for every call to the core API (Person 1, api/openapi.json).
// With NEXT_PUBLIC_API_URL unset, the app uses local mock data. Set it to the API URL
// (http://localhost:8000 locally, the Render URL when deployed) and the adapters below
// turn the API's snake_case / *_cents fields into the shapes in ./types, so pages never change.
import { backerStories, categories, impactUpdates, projects, sponsors } from "./mock-data";
import type { BackerStory, Category, ImpactUpdate, Project, ProjectFilters, Sponsor } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

/** Like get(), but routes Person 1 hasn't built yet (X-Stub header = example data) count as empty */
async function getBuilt<T>(path: string, empty: T): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
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
};
type ApiRound = { ends_at: string };
type ApiStory = { id: number; project_id: number; title: string; body: string; evidence_urls: string[]; created_at: string };

/** The site uses the category name as its id ("health"), the API a number */
const slug = (name: string) => name.trim().toLowerCase();
const money = (cents: number, currency: string) => ({ amount: cents, currency });
/** The API stores facet values in lowercase ("literacy"); show "Literacy" */
const label = (v: string | null, fallback: string) => (v ? v.charAt(0).toUpperCase() + v.slice(1) : fallback);

let roundEnd: Promise<string> | undefined;
function currentRoundEnd() {
  roundEnd ??= get<ApiRound>("/rounds/current")
    .then((r) => r.ends_at)
    .catch(() => new Date(Date.now() + 30 * 86_400_000).toISOString());
  return roundEnd;
}

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
  };
}

async function apiCategories(): Promise<ApiCategory[]> {
  return get<ApiCategory[]>("/categories");
}

// ---- Public functions used by the pages ----

export async function getCategories(): Promise<Category[]> {
  if (!API_URL) return categories;
  const [cats, all] = await Promise.all([apiCategories(), getProjects()]);
  return cats.map((c) => {
    const mine = all.filter((p) => p.categoryId === slug(c.name));
    return {
      id: slug(c.name),
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
    const [rows, endsAt] = await Promise.all([get<ApiProject[]>(`/projects?${params}`), currentRoundEnd()]);
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
  const res = await fetch(`${API_URL}/projects/${id}`, { cache: "no-store" });
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
  const ids = projectId ? [projectId] : (await getProjects()).map((p) => p.id);
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

export async function getSponsors(): Promise<Sponsor[]> {
  return API_URL ? [] : sponsors;
}

export async function getSimilarProjects(p: Project, limit = 3): Promise<Project[]> {
  const all = await getProjects({ category: p.categoryId });
  return all.filter((x) => x.id !== p.id).slice(0, limit);
}

export function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
