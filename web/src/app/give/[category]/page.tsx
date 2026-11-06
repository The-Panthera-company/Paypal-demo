import { notFound } from "next/navigation";
import { FurthestFive } from "@/components/FurthestFive";
import { CategoryCheckout } from "@/components/CategoryCheckout";
import { PageTitle } from "@/components/PageTitle";
import { getCategories, getProjects } from "@/lib/api";

// Rebuilt in the background at most every 30 s, so tab switches serve a ready page.
export const revalidate = 30;

// Category checkout (#20): give to a whole category, preview the split, exclude tags, pay with PayPal.
export default async function GiveToCategory({ params }: { params: Promise<{ category: string }> }) {
  const { category: id } = await params;
  const [categories, projects] = await Promise.all([getCategories(), getProjects({ category: id })]);
  const category = categories.find((c) => c.id === id);
  if (!category) notFound();

  return (
    <>
      <PageTitle title={`Give to ${category.name}`} crumb={category.name} />
      <section className="section bg-surface-alt">
        <div className="container-k">
          <div className="space-y-8">
            <FurthestFive projectIds={projects.map((p) => p.id)} />
            <CategoryCheckout category={category} projects={projects} />
          </div>
        </div>
      </section>
    </>
  );
}
