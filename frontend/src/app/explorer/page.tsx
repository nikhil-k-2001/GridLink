"use client";
import { useMemo, useState } from "react";
import { AlertTriangle, Info } from "lucide-react";
import { useApi } from "@/lib/use-api";
import { useHour } from "@/lib/use-hour";
import { qs } from "@/lib/api";
import type { Page, Provider, Summary, SummarySeries } from "@/lib/types";
import { SOURCE_ORDER, fmtDate, fmtNum, humanise } from "@/lib/format";
import { Empty, ErrorState, Loading, PageHeader, Section } from "@/components/gridlink/page";
import { OriginBadge } from "@/components/gridlink/status";
import { Field, NativeSelect } from "@/components/gridlink/form";
import { ComparisonLineChart, GenerationMixChart } from "@/components/gridlink/charts";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const VIEWS = {
  mix: { label: "Generation by source", metric: "generation" },
  renewables: { label: "Solar & wind", metric: "generation" },
  consumption: { label: "Consumption", metric: "consumption" },
  residual: { label: "Residual load", metric: "residual_load" },
  prices: { label: "Day-ahead prices", metric: "day_ahead_price" },
} as const;
type View = keyof typeof VIEWS;
const RANGES = { "1": "Last 24 hours", "3": "Last 3 days", "7": "Last 7 days", "14": "Last 14 days", "30": "Last 30 days" } as const;

export default function ExplorerPage() {
  const [view, setView] = useState<View>("mix");
  const [days, setDays] = useState<keyof typeof RANGES>("7");
  const [bucket, setBucket] = useState("hour");
  const [country, setCountry] = useState("DE");
  const [providerId, setProviderId] = useState("");
  const [includeSim, setIncludeSim] = useState(true);
  const providers = useApi<Page<Provider>>("/providers?limit=200");

  const hour = useHour();
  const path = hour === null ? null : `/energy-records/summary${qs({
    metric_type: VIEWS[view].metric, country, bucket, include_simulated: includeSim, provider_id: providerId || undefined,
    energy_source: view === "renewables" ? ["solar", "wind_onshore", "wind_offshore"] : undefined,
    start: new Date(hour - Number(days) * 86400_000).toISOString(),
    // day-ahead prices are published for tomorrow: look 36 h ahead
    end: new Date(hour + (view === "prices" ? 36 * 3600_000 : 0)).toISOString(),
  })}`;
  const { data, error, loading } = useApi<Summary>(path);

  const byProvider = useMemo(() => {
    const m = new Map<string, SummarySeries[]>();
    for (const s of data?.series ?? []) {
      const k = `${s.provider_name}${s.data_origin === "simulated" ? " — SIMULATED" : ""}`;
      m.set(k, [...(m.get(k) ?? []), s]);
    }
    return [...m.entries()];
  }, [data]);
  const unit = VIEWS[view].metric === "day_ahead_price" ? "EUR/MWh" : "MW";

  return (
    <div className="space-y-5">
      <PageHeader title="Energy data explorer"
        description="Normalised data from all connectors in canonical units (average MW; EUR/MWh). Every chart shows its provenance and warns when granularity, units, coverage or definitions differ." />

      <Tabs value={view} onValueChange={(v) => setView(v as View)}>
        <TabsList className="flex-wrap">{(Object.keys(VIEWS) as View[]).map((v) => <TabsTrigger key={v} value={v}>{VIEWS[v].label}</TabsTrigger>)}</TabsList>
      </Tabs>

      <div className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-3">
        <Field label="Time range"><NativeSelect value={days} onChange={(e) => setDays(e.target.value as keyof typeof RANGES)}>
          {Object.entries(RANGES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</NativeSelect></Field>
        <Field label="Aggregation"><NativeSelect value={bucket} onChange={(e) => setBucket(e.target.value)}>
          <option value="15min">15 minutes</option><option value="hour">Hourly mean</option><option value="day">Daily mean</option></NativeSelect></Field>
        <Field label="Country"><NativeSelect value={country} onChange={(e) => setCountry(e.target.value)}>
          <option value="DE">Germany (DE)</option><option value="">All countries</option></NativeSelect></Field>
        <Field label="Provider"><NativeSelect value={providerId} onChange={(e) => setProviderId(e.target.value)}>
          <option value="">All providers</option>{providers.data?.items.filter((p) => p.connector_count).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</NativeSelect></Field>
        <label className="flex h-8 items-center gap-2 text-sm"><Switch checked={includeSim} onCheckedChange={setIncludeSim} />Include simulated data</label>
      </div>

      {error ? <ErrorState message={error} /> : (loading && !data) || hour === null ? <Loading /> : !data?.series.length ? (
        <Empty>No data for this selection. Run a connector sync or widen the time range.</Empty>
      ) : (
        <>
          {data.warnings.length > 0 && (
            <div className="space-y-1.5 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
              {data.warnings.map((w) => (
                <div key={w.message} className="flex items-start gap-2"><AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <span><span className="mr-1 text-xs font-semibold uppercase">{w.type}</span>{w.message}</span></div>))}
            </div>
          )}

          {view === "mix" ? byProvider.map(([name, series]) => (
            <Section key={name} title={`${name} — generation by source`}
              description="Stacked within one provider only: definitions are comparable inside a provider, not necessarily across providers.">
              <GenerationMixChart series={series} height={360} />
            </Section>
          )) : (
            <Section title={`${VIEWS[view].label} (${unit})`}
              description={byProvider.length > 1 ? "Dashed lines are simulated. Compare only where the dataset definitions match." : undefined}>
              <ComparisonLineChart series={[...data.series].sort((a, b) => SOURCE_ORDER.indexOf(a.energy_source) - SOURCE_ORDER.indexOf(b.energy_source))} unit={unit} height={340} />
            </Section>
          )}

          <Section title="Series & provenance" description="Where each number comes from, how it was transformed and what it covers.">
            <div className="grid gap-4 lg:grid-cols-2">
              {data.provenance.map((p) => (
                <div key={p.provider_id} className="rounded-lg border p-3 text-sm">
                  <div className="flex items-center justify-between gap-2"><span className="font-medium">{p.provider_name}</span>
                    <span className="flex gap-1">{p.data_origins.map((o) => <OriginBadge key={o} origin={o} />)}</span></div>
                  <div className="mt-1 text-xs text-muted-foreground">Licence: {p.licence ?? "—"} · Attribution: {p.attribution ?? "—"}</div>
                  <div className="mt-1 text-xs text-muted-foreground">Connector: {p.connectors.map((c) => `${c.name} (last sync ${fmtDate(c.last_successful_sync)})`).join("; ")}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-left text-muted-foreground"><tr className="border-b">
                  <th className="py-1.5 pr-3 font-medium">Series</th><th className="pr-3 font-medium">Provider dataset</th>
                  <th className="pr-3 font-medium">Published as</th><th className="pr-3 font-medium">Stored as</th>
                  <th className="pr-3 font-medium">Coverage (UTC)</th><th className="pr-3 text-right font-medium">Records</th><th className="text-right font-medium">No value</th></tr></thead>
                <tbody>{data.series.map((s) => (
                  <tr key={s.key} className="border-b last:border-0">
                    <td className="py-1.5 pr-3">{humanise(s.energy_source)} {s.data_origin === "simulated" && <OriginBadge origin="simulated" className="ml-1" />}</td>
                    <td className="pr-3" title={s.dataset?.description ?? ""}>{s.dataset?.name ?? "—"} <Info className="inline size-3 text-muted-foreground" /></td>
                    <td className="pr-3 font-mono">{s.dataset?.published_unit} / {s.source_interval_minutes.join(",")} min</td>
                    <td className="pr-3 font-mono">{String(s.unit)} (avg)</td>
                    <td className="pr-3">{fmtDate(s.coverage.first)} → {fmtDate(s.coverage.last)}</td>
                    <td className="pr-3 text-right tabular-nums">{fmtNum(s.coverage.records)}</td>
                    <td className={`text-right tabular-nums ${s.coverage.null_values ? "text-amber-700 dark:text-amber-400" : ""}`}>{fmtNum(s.coverage.null_values)}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          </Section>
        </>
      )}
    </div>
  );
}
