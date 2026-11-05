import type { GlobePin } from "@/components/GlobeBackdrop";
import { formatMoney, getProjects } from "./api";
import { placeLocation } from "./places";

/** One pin per active project whose place we can locate (others are simply left off the globe) */
export async function getGlobePins(): Promise<GlobePin[]> {
  const projects = await getProjects().catch(() => []);
  return projects.flatMap((p) => {
    const location = placeLocation(p.facets.region);
    if (!location || p.status === "completed") return [];
    return [{ id: p.id, title: p.title, categoryId: p.categoryId, location, place: p.facets.region, raised: formatMoney(p.raised), goal: formatMoney(p.goal) }];
  });
}
