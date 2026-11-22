"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useApi } from "@/lib/use-api";
import { NEED_LABEL, type Coverage } from "@/lib/types";
import { fmtNum, humanise } from "@/lib/format";
import { ErrorState, Loading, PageHeader, Section, Stat } from "@/components/gridlink/page";
import { NativeSelect } from "@/components/gridlink/form";
import { COVERAGE, CoverageBar, CoverageChip, FICTIONAL_NOTE } from "@/components/gridlink/coverage";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const NEEDS = ["production_metering", "day_ahead_price", "plant_master_data"];

export default function CoveragePage() {
  const { data, error, loading, reload } = useApi<Coverage>("/coverage");
  const [customer, setCustomer] = useState("");
  const [country, setCountry] = useState("");
  const [onlyGaps, setOnlyGaps] = useState(false);

  const rows = useMemo(() => (data?.assets ?? []).filter((a) => (!customer || a.customer === customer) && (!country || a.country_code === country)
    && (!onlyGaps || a.needs.some((n) => n.status !== "covered"))), [data, customer, country, onlyGaps]);

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !data) return <Loading />;
  const t = data.totals;

  return (
    <div className="space-y-5">
      <PageHeader title="Customers & plants"
        description={<>Every plant needs certain data. This is the demand that drives which connections to build — and the status of each one, with the reason and next step. <span className="italic">{FICTIONAL_NOTE}</span></>} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Overall coverage" value={`${t.pct}%`} sub={<><CoverageBar className="my-1.5" covered={t.covered} inProgress={t.in_progress} gaps={t.gaps} />{t.covered} covered · {t.in_progress} in progress · {t.gaps} gaps</>} />
        {NEEDS.filter((n) => data.by_need[n]).map((n) => {
          const r = data.by_need[n];
          return <Stat key={n} label={NEED_LABEL[n]} value={`${r.pct}%`} sub={<><CoverageBar className="my-1.5" covered={r.covered} inProgress={r.in_progress} gaps={r.gaps} />{r.covered}/{r.pairs} plants · {r.mw_pct}% of MW</>} />;
        })}
      </div>

      <Section title="By customer" description="What each account would see if they asked “do you have my data?”">
        <div className="grid gap-3 md:grid-cols-3">{Object.entries(data.by_customer).map(([name, r]) => {
          const plants = data.assets.filter((a) => a.customer === name);
          return (
            <button key={name} onClick={() => setCustomer(customer === name ? "" : name)}
              className={`rounded-lg border p-3 text-left transition-colors hover:bg-muted/50 ${customer === name ? "border-primary ring-1 ring-primary" : ""}`}>
              <div className="flex items-center justify-between"><span className="font-medium">{name}</span><span className="text-sm tabular-nums">{r.pct}%</span></div>
              <div className="mb-2 text-xs text-muted-foreground">{plants.length} plants · {fmtNum(plants.reduce((s, a) => s + a.capacity_mw, 0), 1)} MW · {[...new Set(plants.map((a) => a.country_code))].join(", ")}</div>
              <CoverageBar covered={r.covered} inProgress={r.in_progress} gaps={r.gaps} />
            </button>);
        })}</div>
      </Section>

      <div className="flex flex-wrap items-center gap-2">
        <NativeSelect value={customer} onChange={(e) => setCustomer(e.target.value)} aria-label="Customer">
          <option value="">All customers</option>{Object.keys(data.by_customer).map((c) => <option key={c}>{c}</option>)}</NativeSelect>
        <NativeSelect value={country} onChange={(e) => setCountry(e.target.value)} aria-label="Country">
          <option value="">All countries</option>{Object.keys(data.by_country).map((c) => <option key={c}>{c}</option>)}</NativeSelect>
        <label className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={onlyGaps} onChange={(e) => setOnlyGaps(e.target.checked)} />Only plants with gaps</label>
        <span className="text-xs text-muted-foreground">{rows.length} plants</span>
      </div>

      <div className="overflow-x-auto rounded-xl border bg-card">
        <Table>
          <TableHeader><TableRow>
            <TableHead className="pl-4">Plant</TableHead><TableHead>Customer</TableHead><TableHead className="text-right">MW</TableHead>
            <TableHead>Data holder</TableHead>{NEEDS.map((n) => <TableHead key={n} className="min-w-56">{NEED_LABEL[n]}</TableHead>)}
          </TableRow></TableHeader>
          <TableBody>{rows.map((a) => (
            <TableRow key={a.asset_id} className="align-top">
              <TableCell className="pl-4"><div className="font-medium">{a.name}</div>
                <div className="text-xs text-muted-foreground">{a.country_code} · {a.bidding_zone} · {humanise(a.technology)}</div>
                {a.metering_point_id && <code className="text-[10px] text-muted-foreground">{a.metering_point_id}</code>}</TableCell>
              <TableCell className="text-xs">{a.customer}</TableCell>
              <TableCell className="text-right tabular-nums">{a.capacity_mw}</TableCell>
              <TableCell className="text-xs">{a.dso ?? <span className="text-muted-foreground">—</span>}</TableCell>
              {NEEDS.map((n) => {
                const item = a.needs.find((x) => x.need === n);
                if (!item) return <TableCell key={n} className="text-xs text-muted-foreground">not needed</TableCell>;
                return (
                  <TableCell key={n} className="text-xs whitespace-normal">
                    <div className="flex items-center gap-1.5"><CoverageChip status={item.status} />{item.data_origin === "simulated" && item.status === "covered" &&
                      <span className="text-[10px] text-fuchsia-700 dark:text-fuchsia-300">simulated</span>}</div>
                    <div className="mt-1 text-muted-foreground">{item.reason}</div>
                    {item.status !== "covered" && <Link href={`/countries/${a.country_code}`} className="text-[11px] text-primary hover:underline">Access map →</Link>}
                  </TableCell>);
              })}
            </TableRow>))}</TableBody>
        </Table>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">{Object.keys(COVERAGE).filter((s) => data.status_counts[s]).map((s) =>
        <span key={s} className="inline-flex items-center gap-1"><CoverageChip status={s} />{data.status_counts[s]}</span>)}</div>
    </div>
  );
}
