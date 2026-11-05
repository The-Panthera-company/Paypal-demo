import type { Project } from "@/lib/types";
import { MosaicCard } from "./MosaicCard";

// Mirrored mosaic on a 3-column grid; every 7 cards repeat:
//   [   big   ][tall]     rows 1-2
//   [sq][sq][sq]          row 3
//   [tall][   big   ]     rows 4-5 (mirror)
// A tall tile is a full column wide, so portrait photos keep room for their title. Most urgent
// projects land in the big tiles. Leftovers end flush. Phones: one column; tablets: two.
const PATTERN = [
  { cls: "sm:col-span-2 sm:row-span-2", size: "lg" },
  { cls: "sm:row-span-2", size: "md" },
  { cls: "", size: "sm" },
  { cls: "", size: "sm" },
  { cls: "", size: "sm" },
  { cls: "sm:row-span-2", size: "md" },
  { cls: "sm:col-span-2 sm:row-span-2", size: "lg" },
] as const;
type Shape = { cls: string; size: "lg" | "md" | "sm" };

export function ProjectMosaic({ projects, photos, sort = true }: { projects: Project[]; photos: Record<string, string>; sort?: boolean }) {
  const ordered = sort ? [...projects].sort((a, b) => b.urgency - a.urgency || a.backerCount - b.backerCount) : projects;
  const full = Math.floor(ordered.length / PATTERN.length) * PATTERN.length;
  const tail: Shape[] = [];
  let left = ordered.length - full;
  if (left >= 2) {
    tail.push(PATTERN[0], PATTERN[1]); // big + tall
    left -= 2;
  }
  while (left >= 3) {
    tail.push(PATTERN[2], PATTERN[3], PATTERN[4]); // a row of squares
    left -= 3;
  }
  if (left === 2) tail.push({ cls: "sm:col-span-1 lg:col-span-2", size: "md" }, { cls: "", size: "sm" });
  if (left === 1) tail.push({ cls: "sm:col-span-2 lg:col-span-3", size: "lg" });
  const shape = (i: number): Shape => (i < full ? PATTERN[i % PATTERN.length] : tail[i - full]);

  return (
    <div className="grid auto-rows-[300px] grid-flow-dense gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {ordered.map((p, i) => (
        <div key={p.id} className={shape(i).cls}>
          <MosaicCard project={p} photo={photos[p.id]} size={shape(i).size} />
        </div>
      ))}
    </div>
  );
}
