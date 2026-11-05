import { getGlobePins } from "@/lib/globe";
import { MandateSetup } from "@/components/MandateSetup";
import { PageTitle } from "@/components/PageTitle";
import { getCategories, getProjects } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function MandatePage() {
  const [categories, projects, globe] = await Promise.all([getCategories(), getProjects(), getGlobePins()]);
  const tags = [...new Set(projects.flatMap((p) => p.tags))].sort();
  return (
    <>
      <PageTitle title="Your Giving Agent" crumb="Giving Agent" globe={globe} />
      <section className="section bg-surface-alt">
        <div className="container-k space-y-8">
          <p className="max-w-[70ch] text-lg leading-8">
            Set your causes and limits once. Each month your agent gives to the projects that fit best, explains every choice,
            and asks you before anything above your limit. It can never go outside your rules.
          </p>
          <MandateSetup categories={categories} tags={tags} />
        </div>
      </section>
    </>
  );
}
