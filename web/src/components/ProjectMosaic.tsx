import type { Project } from "@/lib/types";
import { MosaicCard } from "./MosaicCard";
import { ProjectCard } from "./ProjectCard";

// Explore layout. Desktop: two free-flowing columns (masonry) - no row grid, so each card can be
// its own height; heights follow a repeating rhythm, mirrored between the columns. Most urgent
// first. Phones: the standard card with its info always visible.
const HEIGHTS = [520, 380, 440, 600, 400, 480];
const SIZE = (h: number) => (h >= 520 ? "lg" : h >= 440 ? "md" : "sm") as "lg" | "md" | "sm";

export function ProjectMosaic({ projects, photos, sort = true }: { projects: Project[]; photos: Record<string, string>; sort?: boolean }) {
  const ordered = sort ? [...projects].sort((a, b) => b.urgency - a.urgency || a.backerCount - b.backerCount) : projects;
  return (
    <>
      <div className="grid gap-6 sm:hidden">
        {ordered.map((p) => (
          <ProjectCard key={p.id} project={p} photo={photos[p.id]} size="lg" />
        ))}
      </div>
      <div className="hidden gap-5 sm:columns-2 sm:block">
        {ordered.map((p, i) => {
          const h = HEIGHTS[i % HEIGHTS.length];
          return (
            <div key={p.id} className="mb-5 break-inside-avoid" style={{ height: h }}>
              <MosaicCard project={p} photo={photos[p.id]} size={SIZE(h)} />
            </div>
          );
        })}
      </div>
    </>
  );
}
