import { ApplyForm } from "@/components/ApplyForm";
import { PageTitle } from "@/components/PageTitle";
import { getCategories } from "@/lib/api";

export const revalidate = 300;

export default async function ApplyPage() {
  const categories = (await getCategories()).filter((c) => c.apiId !== undefined).map((c) => ({ apiId: c.apiId!, name: c.name }));
  return (
    <>
      <PageTitle title="Apply for funding" crumb="Apply" />
      <section className="section bg-surface-alt">
        <div className="container-k space-y-6">
          <p className="mx-auto max-w-3xl text-lg leading-8">
            Tell us about your project. A person checks every application before it&apos;s listed, and money is released in steps as you upload receipts and photos.
          </p>
          <ApplyForm categories={categories} />
        </div>
      </section>
    </>
  );
}
