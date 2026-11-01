import { ImpactGallery } from "@/components/ImpactGallery";
import { PageTitle } from "@/components/PageTitle";
import { EmptyState } from "@/components/ui";
import { formatDate, getImpactUpdates, getProjects } from "@/lib/api";

export default async function GalleryPage() {
  const [updates, projects] = await Promise.all([getImpactUpdates(), getProjects()]);
  const items = updates.map((u) => ({ ...u, project: projects.find((p) => p.id === u.projectId) }));
  const dateLabels = Object.fromEntries(updates.map((u) => [u.id, formatDate(u.date)]));

  return (
    <>
      <PageTitle title="Impact gallery" crumb="Gallery" />
      <section className="section">
        <div className="container-k">
          <p className="mb-10 max-w-[65ch] text-lg leading-9">
            Every photo and receipt here was uploaded by a project for a milestone and checked before money was released.
          </p>
          {items.length === 0 ? (
            <EmptyState title="No evidence yet" body="Photos and receipts appear here as soon as the first milestone is released." />
          ) : (
            <ImpactGallery items={items} dateLabels={dateLabels} />
          )}
        </div>
      </section>
    </>
  );
}
