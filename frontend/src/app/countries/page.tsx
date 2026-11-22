"use client";
import Link from "next/link";
import { useApi } from "@/lib/use-api";
import type { CountrySummary, LeadTimes } from "@/lib/types";
import { fmtNum } from "@/lib/format";
import { ErrorState, Loading, PageHeader } from "@/components/gridlink/page";
import { CoverageBar, StatusPill } from "@/components/gridlink/coverage";
import { Progress } from "@/components/ui/progress";

export default function CountriesPage() {
  const { data, error, loading, reload } = useApi<{ countries: CountrySummary[]; lead_times: LeadTimes }>("/countries");
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !data) return <Loading />;
  return (
    <div className="space-y-5">
      <PageHeader title="Country access maps"
        description="How data can be accessed in each market: who holds it, which routes exist (with fallbacks), what is blocking, and a 10-step playbook that gets faster with every country." />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.countries.map((c) => (
          <Link key={c.country_code} href={`/countries/${c.country_code}`} className="rounded-xl border bg-card p-4 transition-colors hover:border-primary/50 hover:bg-muted/30">
            <div className="flex items-start justify-between gap-2">
              <div><div className="text-lg font-semibold">{c.name}</div><div className="text-xs text-muted-foreground">{c.bidding_zones.join(" · ")}</div></div>
              <StatusPill status={c.status} />
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <div><div className="text-lg font-semibold tabular-nums">{c.plants}</div><div className="text-[11px] text-muted-foreground">plants</div></div>
              <div><div className="text-lg font-semibold tabular-nums">{fmtNum(c.capacity_mw, 0)}</div><div className="text-[11px] text-muted-foreground">MW</div></div>
              <div><div className="text-lg font-semibold tabular-nums">{c.open_requests}</div><div className="text-[11px] text-muted-foreground">open requests</div></div>
            </div>
            {c.coverage && <div className="mt-3"><div className="mb-1 flex justify-between text-xs"><span>Coverage</span><span className="tabular-nums">{c.coverage.pct}%</span></div>
              <CoverageBar covered={c.coverage.covered} inProgress={c.coverage.in_progress} gaps={c.coverage.gaps} /></div>}
            <div className="mt-3"><div className="mb-1 flex justify-between text-xs"><span>Playbook</span>
              <span className="tabular-nums">{c.playbook.done}/{c.playbook.total}{c.playbook.blocked ? ` · ${c.playbook.blocked} blocked` : ""}</span></div>
              <Progress value={c.playbook.pct} className="h-1.5" /></div>
            <div className="mt-3 text-xs text-muted-foreground">{c.customers.join(", ") || "No customers yet"}</div>
            {data.lead_times.by_country[c.country_code] && <div className="mt-1 text-xs text-muted-foreground">Access granted in {data.lead_times.by_country[c.country_code].median_days} days (median)</div>}
          </Link>
        ))}
      </div>
    </div>
  );
}
