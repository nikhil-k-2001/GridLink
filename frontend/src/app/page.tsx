"use client";
import Link from "next/link";
import { useApi } from "@/lib/use-api";
import { useHour } from "@/lib/use-hour";
import { qs } from "@/lib/api";
import type { Overview, Summary } from "@/lib/types";
import { fmtNum, relTime } from "@/lib/format";
import { Empty, ErrorState, Loading, PageHeader, Section, Stat } from "@/components/gridlink/page";
import { FreshnessBadge, HealthBadge, OriginBadge, StatusDot, SyncStatusBadge } from "@/components/gridlink/status";
import { GenerationMixChart } from "@/components/gridlink/charts";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function OverviewPage() {
  const { data, error, loading, reload } = useApi<Overview>("/overview");
  const hour = useHour();
  const mix = useApi<Summary>(hour === null ? null : `/energy-records/summary${qs({ metric_type: "generation", bucket: "hour",
    include_simulated: false, start: new Date(hour - 3 * 86400_000).toISOString(), end: new Date(hour).toISOString() })}`);

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !data) return <Loading />;
  const c = data.connector_status_counts;
  const names = Object.fromEntries(data.connectors.map((x) => [x.id, x.name]));

  return (
    <div className="space-y-6">
      <PageHeader title="Integration overview"
        description="Connect, standardise, validate and monitor energy data from multiple European markets. Health is computed from stored records, not from HTTP status alone." />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Connectors" value={data.connectors.length}
          sub={<span className="flex flex-wrap gap-x-3">{(["healthy", "warning", "degraded", "failed"] as const).map((s) =>
            <span key={s} className="inline-flex items-center gap-1"><StatusDot status={s} />{c[s]} {s}</span>)}</span>} />
        <Stat label="Records stored" value={fmtNum(data.records.total)}
          sub={`${fmtNum(data.records.by_origin.real ?? 0)} real · ${fmtNum(data.records.by_origin.simulated ?? 0)} simulated`} />
        <Stat label="Providers" value={data.providers.total}
          sub={`${data.providers.by_status.connected ?? 0} connected · ${data.datasets} datasets`} />
        <Stat label="Syncs (7 days)" value={Object.values(data.syncs_last_7d).reduce((a, b) => a + b, 0)}
          sub={`${data.syncs_last_7d.failed ?? 0} failed · ${data.errors_last_7d} errors logged`} />
      </div>

      <Section title="Connector health" description="Status combines sync outcomes, request reliability, completeness, validity and freshness."
        actions={<Link href="/connectors" className="text-xs font-medium text-primary hover:underline">All connectors →</Link>}>
        <div className="-mx-4 -my-4 overflow-x-auto">
          <Table>
            <TableHeader><TableRow>
              <TableHead className="pl-4">Connector</TableHead><TableHead>Status</TableHead><TableHead>Completeness</TableHead>
              <TableHead>Freshness</TableHead><TableHead>Last successful sync</TableHead><TableHead className="pr-4">Primary reason</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data.connectors.map((x) => (
                <TableRow key={x.id}>
                  <TableCell className="pl-4">
                    <Link href={`/connectors/${x.id}`} className="font-medium hover:underline">{x.name}</Link>
                    <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">{x.provider} · {x.country_code}
                      {x.data_origin === "simulated" && <OriginBadge origin="simulated" />}</div>
                  </TableCell>
                  <TableCell><HealthBadge status={x.status} /></TableCell>
                  <TableCell className="tabular-nums">{x.completeness === null ? "—" : `${x.completeness}%`}</TableCell>
                  <TableCell><FreshnessBadge status={x.freshness} /></TableCell>
                  <TableCell className="text-muted-foreground">{relTime(x.last_successful_sync)}</TableCell>
                  <TableCell className="max-w-md pr-4 text-xs whitespace-normal text-muted-foreground">
                    {x.reasons.find((r) => r.level !== "info")?.reason ?? "All checks passed"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Section>

      <div className="grid gap-6 xl:grid-cols-3">
        <Section className="xl:col-span-2" title="German generation mix — last 3 days"
          description="Real SMARD data, hourly mean of quarter-hour values, average MW. Source: Bundesnetzagentur | SMARD.de"
          actions={<Link href="/explorer" className="text-xs font-medium text-primary hover:underline">Explore →</Link>}>
          {mix.loading || hour === null ? <Loading /> : mix.error ? <ErrorState message={mix.error} /> :
            mix.data && mix.data.series.length ? <GenerationMixChart series={mix.data.series} height={300} /> :
              <Empty>No real generation data yet. Run the SMARD connector sync.</Empty>}
        </Section>
        <Section title="Recent syncs">
          <ul className="divide-y text-sm">
            {data.recent_syncs.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <Link href={`/connectors/${s.connector_id}`} className="block truncate hover:underline">{names[s.connector_id] ?? `Connector ${s.connector_id}`}</Link>
                  <span className="text-xs text-muted-foreground">#{s.id} · {relTime(s.started_at)} · {fmtNum(s.records_saved)} saved
                    {s.records_failed ? ` · ${s.records_failed} rejected` : ""}{s.error_code ? ` · ${s.error_code}` : ""}</span>
                </div>
                <SyncStatusBadge status={s.status} />
              </li>
            ))}
            {!data.recent_syncs.length && <li className="py-4 text-muted-foreground">No syncs yet.</li>}
          </ul>
        </Section>
      </div>
    </div>
  );
}
