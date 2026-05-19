import { useQuery } from "@tanstack/react-query";
import { auditExportUrl, listAuditForTenant } from "@/api/extras";

export function AuditPage(): JSX.Element {
  const { data, isLoading, error } = useQuery({
    queryKey: ["audit", "tenant"],
    queryFn: () => listAuditForTenant(),
  });

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <section className="border-b border-rule pb-6 mb-8 flex items-end justify-between">
        <div>
          <div className="byline">Audit log · Append-only · RLS-isolated</div>
          <h2 className="masthead">Audit</h2>
        </div>
        <a
          href={auditExportUrl()}
          className="btn-primary"
          data-testid="audit-export"
          target="_blank"
          rel="noreferrer"
        >
          Export ZIP
        </a>
      </section>

      {isLoading && <p className="font-ui text-sub">Loading…</p>}
      {error && (
        <p className="border border-accent bg-accent/10 p-3 font-ui text-sm text-accent">
          {(error as Error).message}
        </p>
      )}
      {data && (
        <ol
          className="font-mono text-xs space-y-2 max-h-[70vh] overflow-y-auto"
          data-testid="audit-list"
        >
          {data.map((e) => (
            <li key={e.id} className="border-b border-rule pb-2 grid grid-cols-[160px,200px,1fr] gap-3">
              <span className="text-sub">{new Date(e.ts).toLocaleString("en-GB")}</span>
              <span className="text-ink uppercase tracking-wider">{e.kind}</span>
              <span className="text-sub truncate" title={JSON.stringify(e.payload_json)}>
                {JSON.stringify(e.payload_json)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
