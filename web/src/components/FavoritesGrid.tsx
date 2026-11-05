"use client";

import Link from "next/link";
import { useFavorites } from "@/lib/favorites";
import type { Project } from "@/lib/types";
import { ProjectMosaic } from "./ProjectMosaic";

/** The Favourites tab: projects saved with the heart, to review before deciding */
export function FavoritesGrid({ projects, photos }: { projects: Project[]; photos: Record<string, string> }) {
  const { ids } = useFavorites();
  const saved = ids.map((id) => projects.find((p) => p.id === id)).filter((p): p is Project => Boolean(p));
  if (saved.length === 0)
    return (
      <div className="border border-dashed border-line bg-white p-10 text-center">
        <p className="font-display text-2xl text-ink">No favourites yet</p>
        <p className="mx-auto mt-2 max-w-md">Tap the heart on any project to save it here, then compare them before you give.</p>
        <Link href="/projects" className="btn btn-2 mt-6">
          Browse projects
        </Link>
      </div>
    );
  const total = saved.reduce((s, p) => s + Math.max(0, p.goal.amount - p.raised.amount), 0);
  return (
    <div className="space-y-6">
      <p className="text-ink">
        {saved.length} saved · together they still need{" "}
        <strong className="tabular">
          {new Intl.NumberFormat(undefined, { style: "currency", currency: saved[0].goal.currency, maximumFractionDigits: 0 }).format(total / 100)}
        </strong>
      </p>
      <ProjectMosaic projects={saved} photos={photos} sort={false} />
    </div>
  );
}

export function FavoritesCount() {
  const { ids } = useFavorites();
  return ids.length ? <span className="tabular ml-1.5 bg-accent px-1.5 text-xs leading-5 text-ink">{ids.length}</span> : null;
}
