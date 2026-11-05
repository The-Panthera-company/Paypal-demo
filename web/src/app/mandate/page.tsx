import { getGlobePins } from "@/lib/globe";
import { MandateSetup } from "@/components/MandateSetup";
import { doodleTile, doodleUrl } from "@/lib/doodles";
import { PageTitle } from "@/components/PageTitle";
import { getCategories, getProjects } from "@/lib/api";

// Rebuilt in the background at most every 30 s, so tab switches serve a ready page.
export const revalidate = 30;

// Doodle wallpaper behind the page; the content sits on solid cards so it stays easy to read
const WALLPAPER = doodleUrl(doodleTile({ stroke: "#cfe3d8", seed: 23, density: 7 }));

export default async function MandatePage() {
  const [categories, projects, globe] = await Promise.all([getCategories(), getProjects(), getGlobePins()]);
  const tags = [...new Set(projects.flatMap((p) => p.tags))].sort();
  return (
    <>
      <PageTitle title="Your Giving Agent" crumb="Giving Agent" globe={globe} />
      <section className="section bg-surface-alt" style={{ backgroundImage: WALLPAPER, backgroundSize: "340px" }}>
        <div className="container-k space-y-8">
          <p className="mx-auto max-w-3xl border-l-4 border-accent bg-white/95 p-6 text-lg leading-8 shadow-[0_10px_30px_rgba(11,46,51,0.08)]">
            Set your causes and limits once. Each month your agent gives to the projects that fit best, explains every choice,
            and asks you before anything above your limit. It can never go outside your rules.
          </p>
          <MandateSetup categories={categories} tags={tags} />
        </div>
      </section>
    </>
  );
}
