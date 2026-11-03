import { PageTitle } from "./PageTitle";

export function ComingSoon({ title, issue }: { title: string; issue: number }) {
  return (
    <>
      <PageTitle title={title} crumb={title} />
      <section className="section">
        <div className="container-k">
          <p className="text-lg">Coming soon (issue #{issue}).</p>
        </div>
      </section>
    </>
  );
}
