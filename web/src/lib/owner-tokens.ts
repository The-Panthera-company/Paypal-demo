"use client";

// Owner tokens for projects applied from this browser, keyed by project id. A per-browser
// convenience only: the token is shown once, and an admin can issue a new one if it's lost.
const KEY = "cg:owner-tokens";
export type SavedProject = { token: string; title: string; milestones: { id: number; title: string; amount_cents: number }[]; savedAt: string };

function all(): Record<string, SavedProject> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}");
  } catch {
    return {};
  }
}
export function saveOwner(projectId: string, p: SavedProject) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...all(), [projectId]: p }));
  } catch {
    /* storage blocked: the user still has the token on screen */
  }
}
export function loadOwner(projectId: string): SavedProject | null {
  return all()[projectId] ?? null;
}
