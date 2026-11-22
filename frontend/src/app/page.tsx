"use client";
import Link from "next/link";
import { ArrowRight, Clock, Mail } from "lucide-react";
import { useApi } from "@/lib/use-api";
import { NEED_LABEL, type Cockpit } from "@/lib/types";
import { fmtNum, relTime } from "@/lib/format";
import { Empty, ErrorState, Loading, PageHeader, Section, Stat } from "@/components/gridlink/page";
import { HealthBadge, OriginBadge } from "@/components/gridlink/status";
import { CoverageBar, FICTIONAL_NOTE, SeverityBadge, StatusPill } from "@/components/gridlink/coverage";

const COUNTRY: Record<string, string> = { DE: "Germany", FR: "France", ES: "Spain", IT: "Italy", NL: "Netherlands" };

export default function CockpitPage() {
  const { data, error, loading, reload } = useApi<Cockpit>("/cockpit");
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !data) return <Loading />;
  const c = data.coverage;
  const overdue = data.follow_ups.overdue;

  return (
    <div className="space-y-6">
      <PageHeader title="This week in market connections"
        description={<>What needs attention: customer data gaps, providers to chase, and data issues affecting customers. <span className="italic">{FICTIONAL_NOTE}</span></>} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Data coverage" value={`${c.pct ?? 0}%`}
          sub={<><CoverageBar className="my-1.5" covered={c.covered} inProgress={c.in_progress} gaps={c.gaps} />{c.covered} of {c.pairs} plant data needs · {c.mw_pct}% of MW</>} />
        <Stat label="Plants under management" value={c.plants} sub={`${fmtNum(c.capacity_mw, 1)} MW · 3 customers · 5 countries`} />
        <Stat label="Follow-ups overdue" value={<span className={overdue.length ? "text-red-700 dark:text-red-400" : ""}>{overdue.length}</span>}
          sub={`${data.follow_ups.upcoming.length} upcoming`} />
        <Stat label="Open data issues" value={data.issues.open} sub={`${data.issues.high} high severity`} />
        <Stat label="Median time to access" value={data.lead_times.median_days_to_grant === null ? "—" : `${data.lead_times.median_days_to_grant} d`}
          sub={`request → granted · ${data.lead_times.samples} samples`} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Section title="Chase today" description="Open access requests past their follow-up or due date."
          actions={<Link href="/relationships" className="text-xs font-medium text-primary hover:underline">Relationships →</Link>}>
          {overdue.length ? (
            <ul className="divide-y text-sm">{overdue.map((f) => (
              <li key={f.request_id} className="flex items-start justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <div className="font-medium">{f.provider} <span className="font-mono text-xs text-muted-foreground">{f.country_code}</span></div>
                  <div className="truncate text-xs text-muted-foreground">{f.subject}</div>
                  <div className="mt-0.5 flex items-center gap-1 text-xs text-red-700 dark:text-red-400"><Clock className="size-3" />
                    {f.next_follow_up ? `follow-up was due ${relTime(f.next_follow_up)}` : `due ${relTime(f.due_date)}`} · last contact {f.days_since_contact ?? "—"} d ago · open {f.days_open} d</div>
                </div>
                <StatusPill status={f.status} />
              </li>))}</ul>
          ) : <Empty>Nothing overdue.</Empty>}
        </Section>

        <Section title="Data issues by customer impact" description="Detected automatically at ingestion; owned until resolved."
          actions={<Link href="/issues" className="text-xs font-medium text-primary hover:underline">All issues →</Link>}>
          {data.issues.top.length ? (
            <ul className="divide-y text-sm">{data.issues.top.map((i) => (
              <li key={i.id} className="flex items-start justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <Link href={`/issues?id=${i.id}`} className="line-clamp-2 font-medium hover:underline">{i.title}</Link>
                  <div className="text-xs text-muted-foreground">{i.affected_customers.length ? `${i.affected_customers.join(", ")} · ${i.affected_mw} MW` : "No plant-level impact"} · {relTime(i.detected_at)}</div>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1"><SeverityBadge severity={i.severity} /><StatusPill status={i.status} /></div>
              </li>))}</ul>
          ) : <Empty>No open issues.</Empty>}
        </Section>
      </div>

      <Section title="Biggest coverage gaps" description="Uncovered customer demand by country and data need — the input to prioritisation."
        actions={<Link href="/prioritisation" className="text-xs font-medium text-primary hover:underline">Prioritisation →</Link>}>
        <div className="-mx-4 -my-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b text-left text-xs text-muted-foreground">
              <th className="py-2 pr-3 pl-4 font-medium">Country</th><th className="pr-3 font-medium">Data need</th>
              <th className="pr-3 text-right font-medium">Plants</th><th className="pr-3 text-right font-medium">MW</th>
              <th className="pr-3 font-medium">Customers waiting</th><th className="pr-4 font-medium" /></tr></thead>
            <tbody>{data.biggest_gaps.map((g) => (
              <tr key={`${g.country_code}-${g.need}`} className="border-b last:border-0">
                <td className="py-2 pr-3 pl-4">{COUNTRY[g.country_code] ?? g.country_code}</td>
                <td className="pr-3">{NEED_LABEL[g.need] ?? g.need}</td>
                <td className="pr-3 text-right tabular-nums">{g.plants}</td>
                <td className="pr-3 text-right tabular-nums">{fmtNum(g.capacity_mw, 1)}</td>
                <td className="pr-3 text-xs text-muted-foreground">{g.customers.join(", ")}</td>
                <td className="pr-4 text-right"><Link href={`/countries/${g.country_code}`} className="inline-flex items-center gap-1 text-xs text-primary hover:underline">Access map<ArrowRight className="size-3" /></Link></td>
              </tr>))}</tbody>
          </table>
        </div>
      </Section>

      <div className="grid gap-6 xl:grid-cols-3">
        <Section title="Coverage by country">
          <ul className="space-y-3 text-sm">{Object.entries(data.by_country).map(([cc, r]) => (
            <li key={cc}><div className="mb-1 flex justify-between"><Link href={`/countries/${cc}`} className="hover:underline">{COUNTRY[cc] ?? cc}</Link>
              <span className="text-xs tabular-nums text-muted-foreground">{r.covered}/{r.pairs} · {r.pct}%</span></div>
              <CoverageBar covered={r.covered} inProgress={r.in_progress} gaps={r.gaps} /></li>))}</ul>
          <p className="mt-3 text-[11px] text-muted-foreground"><span className="text-emerald-600">■</span> covered <span className="text-sky-500">■</span> in progress <span className="text-orange-500">■</span> gap</p>
        </Section>
        <Section title="Waiting on plant owners" description="Authorisations GridLink needs from customers.">
          {data.authorisations_pending.length ? <ul className="divide-y text-sm">{data.authorisations_pending.map((a) => (
            <li key={a.asset} className="flex items-center justify-between gap-2 py-2"><div><div>{a.asset}</div>
              <div className="text-xs text-muted-foreground">{a.customer} · {a.country_code}</div></div>
              <span className="inline-flex items-center gap-1 text-xs text-sky-700 dark:text-sky-300"><Mail className="size-3" />{a.status === "awaiting_authorisation" ? "Requested" : "Ask owner"}</span></li>))}</ul>
            : <Empty>None pending.</Empty>}
        </Section>
        <Section title="Connector health" actions={<Link href="/connectors" className="text-xs font-medium text-primary hover:underline">Connectors →</Link>}>
          <ul className="divide-y text-sm">{data.connectors.map((x) => (
            <li key={x.id} className="py-2"><div className="flex items-center justify-between gap-2">
              <Link href={`/connectors/${x.id}`} className="truncate hover:underline">{x.name}</Link>
              <span className="flex shrink-0 gap-1">{x.data_origin === "simulated" && <OriginBadge origin="simulated" />}<HealthBadge status={x.status} /></span></div>
              {x.reason && <div className="line-clamp-1 text-xs text-muted-foreground">{x.reason}</div>}</li>))}</ul>
        </Section>
      </div>
    </div>
  );
}
