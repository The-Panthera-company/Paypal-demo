import { EvidenceUploads } from "@/components/EvidenceUploads";
import { PageTitle } from "@/components/PageTitle";
import { getProject } from "@/lib/api";

export const dynamic = "force-dynamic";

// Evidence uploads for the project owner. Works before verification too (the project is
// hidden then, so its milestones come from the application saved in this browser).
export default async function EvidencePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const p = await getProject(id).catch(() => undefined);
  const listed = p
    ? { title: p.title, milestones: (p.milestones ?? []).map((m) => ({ id: Number(m.id), seq: m.seq, title: m.title, amount_cents: m.amount.amount, status: m.status, due_date: m.dueDate })) }
    : null;
  return (
    <>
      <PageTitle title="Upload evidence" crumb="Evidence" />
      <section className="section bg-surface-alt">
        <div className="container-k">
          <EvidenceUploads projectId={id} listed={listed} />
        </div>
      </section>
    </>
  );
}
