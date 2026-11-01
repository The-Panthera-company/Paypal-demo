import Link from "next/link";
import { formatMoney, getCategories } from "@/lib/api";

export default async function Home() {
  const categories = await getCategories();
  return (
    <div className="space-y-10">
      <section className="space-y-3">
        <h1 className="text-3xl font-bold">Small gifts, decided together.</h1>
        <p className="max-w-2xl opacity-80">
          Back verified community projects through PayPal. Projects with many backers earn the biggest share of the
          matching pool, and every shilling is tracked to the receipt.
        </p>
      </section>
      <section>
        <h2 className="mb-4 text-xl font-semibold">Categories</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {categories.map((c) => (
            <Link
              key={c.id}
              href={`/projects?category=${c.id}`}
              className="rounded-lg border border-black/10 p-5 hover:border-black/30 dark:border-white/10 dark:hover:border-white/30"
            >
              <div className="text-lg font-semibold">{c.name}</div>
              <div className="text-sm opacity-70">{c.projectCount} projects</div>
              <div className="mt-2 text-sm">{formatMoney(c.raised)} raised</div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
