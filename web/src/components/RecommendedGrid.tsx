"use client";

import { useFavorites } from "@/lib/favorites";
import type { Project } from "@/lib/types";
import { ProjectMosaic } from "./ProjectMosaic";

// "AI recommended": projects picked for this visitor. Scores like the Giving Agent's weights:
// causes and groups of their favourites, urgency, few backers (each gift counts more in
// matching), and how far from the goal. Saved projects are left out. Explains its picks.
export function RecommendedGrid({ projects, photos }: { projects: Project[]; photos: Record<string, string> }) {
  const { ids } = useFavorites();
  const saved = projects.filter((p) => ids.includes(p.id));
  const likes = new Set(saved.flatMap((p) => [p.categoryId, p.facets.cause, p.facets.group]));
  const score = (p: Project) =>
    (likes.has(p.categoryId) ? 3 : 0) + (likes.has(p.facets.cause) ? 2 : 0) + (likes.has(p.facets.group) ? 1 : 0) + p.urgency + (p.backerCount < 5 ? 2 : 0) + (1 - p.raised.amount / p.goal.amount);
  const picks = projects
    .filter((p) => !ids.includes(p.id) && p.status !== "completed")
    .sort((a, b) => score(b) - score(a))
    .slice(0, 6);
  return (
    <div className="space-y-5">
      <p className="border-l-4 border-primary bg-white p-4 text-sm text-ink">
        {saved.length
          ? `Picked from the causes you saved (${[...new Set(saved.map((p) => p.categoryId))].join(", ")}), then the most urgent projects with the fewest backers, where your gift unlocks the most matching.`
          : "Picked for urgency and few backers, where your gift unlocks the most matching. Save a few favourites and these picks follow what you care about."}
      </p>
      <ProjectMosaic projects={picks} photos={photos} sort={false} />
    </div>
  );
}
