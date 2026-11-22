"use client";
import Link from "next/link";
import { Fragment, useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useApi } from "@/lib/use-api";
import { qs } from "@/lib/api";
import type { Connector, Page, QualityReport } from "@/lib/types";
import { fmtDate, fmtNum, humanise } from "@/lib/format";
import { Empty, ErrorState, Loading, PageHeader, Section } from "@/components/gridlink/page";
import { FreshnessBadge, HealthBadge, OriginBadge, QualityBadge } from "@/components/gridlink/status";
import { NativeSelect } from "@/components/gridlink/form";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

type Dim = { label: string; status: "pass" | "warn" | "fail"; lines: string[] };

function dimensions(r: QualityReport, c?: Connector): Dim[] {
  const v = r.validation_details;
  const weak = (v.series ?? []).filter((s) => s.completeness < 90);
  const comp = r.completeness_score;
  const unmapped = Object.keys(v.consistency?.unmapped_series ?? {});
  const consistencyIssues = (v.consistency?.duplicates ?? 0) + (v.consistency?.unexpected_units ?? 0) +
    (v.consistency?.invalid_country_codes ?? 0) + (v.consistency?.inconsistent_categories ?? 0);
  const invalid = v.validity?.invalid_records ?? 0;
  const rejected = v.validity?.rejected_in_normalisation ?? 0;
  const h = c?.health;
  return [
    { label: "Completeness", status: comp === null ? "warn" : comp < 90 ? "fail" : comp < 98 || weak.length ? "warn" : "pass",
      lines: [`${comp ?? "—"}% of expected intervals present`, `${fmtNum(r.missing_interval_count)} missing intervals · ${fmtNum(r.null_value_count)} null values`,
        ...(v.completeness?.missing_series?.length ? [`Missing series: ${v.completeness.missing_series.join(", ")}`] : []),
        ...weak.slice(0, 3).map((s) => `${s.series_key}: ${s.completeness}%`)] },
    { label: "Consistency", status: consistencyIssues ? "warn" : unmapped.length ? "warn" : "pass",
      lines: [`${v.consistency?.duplicates ?? 0} duplicates (${v.consistency?.conflicting_duplicates ?? 0} conflicting)`,
        `${v.consistency?.unexpected_units ?? 0} unexpected units · ${v.consistency?.invalid_country_codes ?? 0} invalid country codes`,
        `${v.consistency?.inconsistent_categories ?? 0} inconsistent categories`, ...(unmapped.length ? [`Unmapped series: ${unmapped.join(", ")}`] : [])] },
    { label: "Freshness", status: r.freshness_status === "fresh" ? "pass" : r.freshness_status === "delayed" ? "warn" : "fail",
      lines: [`At ingestion: ${r.freshness_status}`, ...(h ? [`Now: ${h.freshness.status}`] : [])] },
    { label: "Validity", status: invalid + rejected === 0 ? "pass" : (invalid + rejected) / Math.max(1, h?.records_fetched_last_sync ?? 1) > 0.05 ? "fail" : "warn",
      lines: [`${invalid} records failed validation · ${rejected} rejected in normalisation`,
        ...Object.entries(v.validity?.by_rule ?? {}).map(([k, n]) => `${humanise(k)}: ${n}`)] },
    { label: "Reliability", status: !h || h.sync_success_rate === null ? "warn" : (h.sync_success_rate < 80 || (h.request_success_rate ?? 100) < 90) ? "fail"
        : (h.sync_success_rate < 95 || (h.request_success_rate ?? 100) < 100 || h.retry_count) ? "warn" : "pass",
      lines: h ? [`Sync success ${h.sync_success_rate ?? "—"}% (last ${h.syncs_considered})`,
        h.request_success_rate === null ? "No HTTP requests (fixture replay)" : `Request success ${h.request_success_rate}% · ${h.retry_count} retries`,
        `Last success ${fmtDate(h.last_successful_sync)}`, `Last failure ${fmtDate(h.last_failed_sync)}`] : ["No data"] },
  ];
}

const DIM_CLS = { pass: "border-emerald-200 dark:border-emerald-900", warn: "border-amber-300 dark:border-amber-900", fail: "border-red-300 dark:border-red-900" };

export default function QualityPage() {
  const connectors = useApi<Page<Connector>>("/connectors?limit=100");
  const [connectorId, setConnectorId] = useState("");
  const [status, setStatus] = useState("");
  const reports = useApi<Page<QualityReport>>(`/quality-reports${qs({ connector_id: connectorId, overall_status: status, limit: 100 })}`);
  const all = useApi<Page<QualityReport>>("/quality-reports?limit=200");
  const [open, setOpen] = useState<number | null>(null);

  const latestByConnector = useMemo(() => {
    const m = new Map<number, QualityReport>();
    for (const r of all.data?.items ?? []) if (!m.has(r.connector_id)) m.set(r.connector_id, r);
    return m;
  }, [all.data]);

  if (connectors.error) return <ErrorState message={connectors.error} onRetry={connectors.reload} />;
  if (!connectors.data || !all.data) return <Loading />;

  return (
    <div className="space-y-6">
      <PageHeader title="Data quality monitoring"
        description="A quality report is generated after every ingestion across five dimensions. Invalid data is rejected with a logged reason — never silently converted." />

      {connectors.data.items.map((c) => {
        const r = latestByConnector.get(c.id);
        return (
          <Section key={c.id} title={c.connector_name}
            description={r ? `Latest report #${r.id} · ${fmtDate(r.created_at)}` : "No quality report yet"}
            actions={<div className="flex items-center gap-1.5">{c.data_origin === "simulated" && <OriginBadge origin="simulated" />}
              {c.health && <HealthBadge status={c.health.status} />}{r && <QualityBadge status={r.overall_status} />}
              <Link href={`/connectors/${c.id}`} className="ml-1 text-xs font-medium text-primary hover:underline">Details →</Link></div>}>
            {r ? (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                {dimensions(r, c).map((d) => (
                  <div key={d.label} className={cn("rounded-lg border-l-4 border bg-background p-3", DIM_CLS[d.status])}>
                    <div className="mb-1.5 flex items-center justify-between"><span className="text-sm font-medium">{d.label}</span><QualityBadge status={d.status} /></div>
                    <ul className="space-y-0.5 text-xs text-muted-foreground">{d.lines.map((l) => <li key={l}>{l}</li>)}</ul>
                  </div>
                ))}
              </div>
            ) : <Empty>{c.health?.reasons[0]?.reason ?? "Run a sync to generate a quality report."}</Empty>}
          </Section>
        );
      })}

      <Section title="Report history" actions={
        <div className="flex gap-2">
          <NativeSelect value={connectorId} onChange={(e) => setConnectorId(e.target.value)} aria-label="Connector">
            <option value="">All connectors</option>{connectors.data.items.map((c) => <option key={c.id} value={c.id}>{c.connector_name}</option>)}</NativeSelect>
          <NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="">All results</option><option value="pass">Pass</option><option value="warn">Warning</option><option value="fail">Fail</option></NativeSelect>
        </div>}>
        {!reports.data ? <Loading /> : !reports.data.items.length ? <Empty>No reports.</Empty> : (
          <div className="-mx-4 -my-4 overflow-x-auto">
            <Table>
              <TableHeader><TableRow><TableHead className="w-8 pl-4" /><TableHead>Report</TableHead><TableHead>Connector</TableHead>
                <TableHead>Result</TableHead><TableHead className="text-right">Completeness</TableHead><TableHead>Freshness</TableHead>
                <TableHead className="text-right">Missing intervals</TableHead><TableHead className="text-right">Duplicates</TableHead>
                <TableHead className="pr-4 text-right">Invalid</TableHead></TableRow></TableHeader>
              <TableBody>{reports.data.items.map((r) => (
                <Fragment key={r.id}>
                  <TableRow className="cursor-pointer" onClick={() => setOpen(open === r.id ? null : r.id)}>
                    <TableCell className="pl-4">{open === r.id ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}</TableCell>
                    <TableCell className="text-xs">#{r.id} · {fmtDate(r.created_at)}</TableCell>
                    <TableCell className="text-xs">{r.connector_name}</TableCell>
                    <TableCell><QualityBadge status={r.overall_status} /></TableCell>
                    <TableCell className="text-right tabular-nums">{r.completeness_score ?? "—"}%</TableCell>
                    <TableCell><FreshnessBadge status={r.freshness_status} /></TableCell>
                    <TableCell className="text-right tabular-nums">{fmtNum(r.missing_interval_count)}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.duplicate_count}</TableCell>
                    <TableCell className="pr-4 text-right tabular-nums">{r.invalid_record_count}</TableCell>
                  </TableRow>
                  {open === r.id && (
                    <TableRow><TableCell colSpan={9} className="bg-muted/40 px-4">
                      <pre className="max-h-80 overflow-auto text-[11px]">{JSON.stringify({ ...r.validation_details, series: `${r.validation_details.series?.length ?? 0} series (see connector page)` }, null, 2)}</pre>
                    </TableCell></TableRow>
                  )}
                </Fragment>
              ))}</TableBody>
            </Table>
          </div>
        )}
      </Section>
    </div>
  );
}
