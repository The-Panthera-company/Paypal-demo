// One place for every call to the core API.
// With NEXT_PUBLIC_API_URL unset, the app uses local mock data; set it to the
// Postman mock URL, then to the real API, without touching the pages.
import { categories, projects } from "./mock-data";
import type { Category, Project, ProjectFilters } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export async function getCategories(): Promise<Category[]> {
  if (!API_URL) return categories;
  return get<Category[]>("/categories");
}

export async function getProjects(filters: ProjectFilters = {}): Promise<Project[]> {
  if (API_URL) {
    const params = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v) as [string, string][],
    );
    return get<Project[]>(`/projects?${params}`);
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
  return get<Project>(`/projects/${id}`);
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
