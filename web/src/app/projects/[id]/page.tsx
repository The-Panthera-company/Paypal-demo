import { notFound } from "next/navigation";
import { formatMoney, getProject } from "@/lib/api";

// Day 1 stub; full project page in issue #11, PayPal button in issue #14.
export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const project = await getProject(id);
  if (!project) notFound();
  return (
    <article className="space-y-4">
      <h1 className="text-2xl font-bold">{project.title}</h1>
      <p className="text-sm opacity-70">Facilitated by {project.facilitator}</p>
      <p>{project.summary}</p>
      <p>
        {formatMoney(project.raised)} raised of {formatMoney(project.goal)} from {project.backerCount} backers
      </p>
    </article>
  );
}
