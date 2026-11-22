"use client";
import Link from "next/link";
import { useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { triggerSync } from "@/lib/sync";
import { useApi } from "@/lib/use-api";
import type { Connector, Page } from "@/lib/types";
import { fmtNum, relTime } from "@/lib/format";
import { ErrorState, Loading, PageHeader } from "@/components/gridlink/page";
import { FreshnessBadge, HealthBadge, OriginBadge } from "@/components/gridlink/status";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function ConnectorsPage() {
  const { data, error, loading, reload } = useApi<Page<Connector>>("/connectors?limit=100");
  const [busy, setBusy] = useState<number | null>(null);

  async function sync(c: Connector) {
    setBusy(c.id);
    await triggerSync(c);
    setBusy(null);
    reload();
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Connectors"
        description="Every connector implements the same contract (authenticate → fetch → parse → normalise → validate → save → health). A connector is only healthy when data is complete, valid and fresh — an HTTP 200 is not enough." />
      {error ? <ErrorState message={error} onRetry={reload} /> : loading && !data ? <Loading /> : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <Table>
            <TableHeader><TableRow>
              <TableHead className="pl-4">Connector</TableHead><TableHead>Provider</TableHead><TableHead>Status</TableHead>
              <TableHead>Last successful sync</TableHead><TableHead>Freshness</TableHead><TableHead className="text-right">Completeness</TableHead>
              <TableHead className="text-right">Request success</TableHead><TableHead className="text-right">Failed records</TableHead>
              <TableHead>Recent error</TableHead><TableHead className="pr-4" />
            </TableRow></TableHeader>
            <TableBody>
              {data?.items.map((c) => {
                const h = c.health!;
                return (
                  <TableRow key={c.id}>
                    <TableCell className="pl-4"><Link href={`/connectors/${c.id}`} className="font-medium hover:underline">{c.connector_name}</Link>
                      <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground"><code>{c.connector_type}</code>
                        {c.data_origin === "simulated" && <OriginBadge origin="simulated" />}</div></TableCell>
                    <TableCell className="text-xs">{c.provider_name}<div className="font-mono text-muted-foreground">{c.country_code}</div></TableCell>
                    <TableCell><HealthBadge status={h.status} /></TableCell>
                    <TableCell className="text-xs text-muted-foreground">{relTime(c.last_successful_sync)}</TableCell>
                    <TableCell><FreshnessBadge status={h.freshness.status} /></TableCell>
                    <TableCell className="text-right tabular-nums">{h.completeness === null ? "—" : `${h.completeness}%`}</TableCell>
                    <TableCell className="text-right tabular-nums">{h.request_success_rate === null ? "—" : `${h.request_success_rate}%`}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtNum(h.failed_records_last_sync)}</TableCell>
                    <TableCell className="max-w-64 truncate text-xs text-muted-foreground" title={h.recent_errors[0]?.message}>{h.recent_errors[0]?.code ?? "—"}</TableCell>
                    <TableCell className="pr-4 text-right">
                      <Button size="sm" variant="outline" disabled={busy !== null || c.status === "paused"} onClick={() => sync(c)}>
                        {busy === c.id ? <Loader2 className="animate-spin" /> : <RefreshCw />}Sync</Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
