"use client";

import Link from "next/link";
import { useFavorites } from "@/lib/favorites";
import { notify } from "./Status";

// Heart on a project card: save it to review before deciding (Favourites tab on Explore).
export function FavoriteButton({ id, title, className = "" }: { id: string; title: string; className?: string }) {
  const fav = useFavorites();
  const on = fav.has(id);
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={on ? `Remove ${title} from favourites` : `Save ${title} to favourites`}
      title={on ? "Saved to favourites" : "Save to favourites"}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        const added = fav.toggle(id);
        notify(added ? `${title} saved to your favourites.` : `${title} removed from your favourites.`, added ? "success" : "info");
      }}
      className={`grid size-11 place-items-center bg-white/90 shadow transition-transform hover:scale-110 ${on ? "text-cat-health" : "text-ink"} ${className}`}
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill={on ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden>
        <path d="M12 20s-7-4.4-7-10a4 4 0 017-2.6A4 4 0 0119 10c0 5.6-7 10-7 10z" />
      </svg>
    </button>
  );
}

/** Header heart with the number saved */
export function FavoritesLink() {
  const { ids } = useFavorites();
  return (
    <Link href="/projects?tab=favorites" className="relative grid size-11 place-items-center text-white hover:text-accent" aria-label={`Favourites (${ids.length} saved)`}>
      <svg width="24" height="24" viewBox="0 0 24 24" fill={ids.length ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden>
        <path d="M12 20s-7-4.4-7-10a4 4 0 017-2.6A4 4 0 0119 10c0 5.6-7 10-7 10z" />
      </svg>
      {ids.length > 0 && <span className="tabular absolute -right-0.5 -top-0.5 grid min-w-5 place-items-center bg-accent px-1 text-[11px] font-bold leading-5 text-ink">{ids.length}</span>}
    </Link>
  );
}
