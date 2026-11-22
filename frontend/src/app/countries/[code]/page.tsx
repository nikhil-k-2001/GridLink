"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ExternalLink, KeyRound, Plus } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { NEED_LABEL, type AccessRoute, type CountryDetail } from "@/lib/types";
import { fmtDate, fmtNum, humanise } from "@/lib/format";
import { Empty, ErrorState, KV, Loading, PageHeader, Section } from "@/components/gridlink/page";
import { EvidenceBadge } from "@/components/gridlink/status";
import { CoverageBar, CoverageChip, StatusPill } from "@/components/gridlink/coverage";
import { Field, NativeSelect } from "@/components/gridlink/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const ROUTE_STATUSES = ["to_investigate", "investigating", "testing", "available", "in_use", "blocked", "rejected"];
const COUNTRY_STATUSES = ["not_started", "mapping", "access_in_progress", "partially_connected", "connected", "blocked"];
const STEP_STATUSES = ["todo", "in_progress", "done", "blocked", "n/a"];
const NEEDS = ["production_metering", "day_ahead_price", "plant_master_data"];

export default function CountryPage() {
  const { code } = useParams<{ code: string }>();
  const { data, error, loading, reload } = useApi<CountryDetail>(`/countries/${code}`);
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !data) return <Loading />;
  const p = data.profile;

  async function patch(path: string, body: unknown, ok?: string) {
    try { await api(path, { method: "PATCH", json: body }); if (ok) toast.success(ok); reload(); }
    catch (e) { toast.error((e as Error).message); }
  }

  return (
    <div className="space-y-6">
      <PageHeader title={`${p.name} — data access map`}
        description={p.summary}
        actions={<NativeSelect value={p.status} aria-label="Country status" onChange={(e) => patch(`/countries/${p.country_code}`, { status: e.target.value }, "Country status updated")}>
          {COUNTRY_STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}</NativeSelect>} />

      <div className="grid gap-6 xl:grid-cols-3">
        <Section title="Market landscape" className="xl:col-span-2">
          <KV items={[["TSO", p.tso], ["Market operator", p.market_operator], ["Bidding zones", p.bidding_zones.join(", ")],
            ["Working languages", p.languages.join(", ")], ["Owner", p.owner], ["Last updated", fmtDate(p.updated_at)]]} />
          <div className="mt-4"><div className="text-xs text-muted-foreground">DSO / metering landscape</div><p className="mt-0.5 text-sm">{p.dso_landscape}</p></div>
        </Section>
        <Section title="Status">
          {data.coverage && <div className="mb-4"><div className="mb-1 flex justify-between text-sm"><span>Customer data coverage</span><span className="tabular-nums">{data.coverage.pct}%</span></div>
            <CoverageBar covered={data.coverage.covered} inProgress={data.coverage.in_progress} gaps={data.coverage.gaps} />
            <div className="mt-1 text-xs text-muted-foreground">{data.coverage.covered} covered · {data.coverage.in_progress} in progress · {data.coverage.gaps} gaps</div></div>}
          <KV items={[["Plants", `${data.plants.length} · ${fmtNum(data.plants.reduce((s, a) => s + a.capacity_mw, 0), 1)} MW`],
            ["Playbook", `${data.playbook_progress.done}/${data.playbook_progress.total} steps done`],
            ["Access lead time", data.lead_times ? `${data.lead_times.median_days} days (median, n=${data.lead_times.samples})` : "No access granted yet"]]} />
        </Section>
      </div>

      <Section title="Access routes" description="For each data need: the primary route and fallbacks. When the official channel stalls, the fallback is already mapped.">
        <div className="space-y-5">{NEEDS.map((need) => {
          const routes = data.routes.filter((r) => r.data_need === need);
          if (!routes.length && need === "plant_master_data") return null;
          return (
            <div key={need}>
              <div className="mb-2 text-sm font-semibold">{NEED_LABEL[need]}</div>
              {routes.length ? <div className="grid gap-3 lg:grid-cols-2">{routes.map((r) => <RouteCard key={r.id} r={r} onPatch={patch} />)}</div>
                : <Empty>No route identified yet.</Empty>}
            </div>);
        })}</div>
        <AddRoute country={p.country_code} onAdded={reload} />
      </Section>

      <div className="grid gap-6 xl:grid-cols-2">
        <Section title="Country playbook" description="The same 10 steps for every market. Notes capture what was different here.">
          <ol className="space-y-2">{data.playbook.map((s) => (
            <li key={s.key} className={cn("rounded-lg border p-2.5", s.status === "done" && "bg-emerald-50/50 dark:bg-emerald-950/20", s.status === "blocked" && "border-orange-300 dark:border-orange-900")}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0"><div className="text-sm font-medium"><span className="mr-1.5 text-muted-foreground tabular-nums">{s.number}.</span>{s.title}</div>
                  <div className="text-xs text-muted-foreground">{s.description}</div>
                  {s.completed_at && <div className="text-[11px] text-muted-foreground">Done {fmtDate(s.completed_at, false)}</div>}</div>
                <NativeSelect value={s.status} aria-label={`${s.title} status`} className="h-7 shrink-0 text-xs"
                  onChange={(e) => patch(`/countries/${p.country_code}/playbook/${s.key}`, { status: e.target.value })}>
                  {STEP_STATUSES.map((x) => <option key={x} value={x}>{humanise(x)}</option>)}</NativeSelect>
              </div>
            </li>))}</ol>
        </Section>

        <div className="space-y-6">
          <Lessons country={p.country_code} initial={p.lessons_learned ?? ""} key={p.updated_at} onSaved={reload} />
          <Section title="Access requests" actions={<Link href="/relationships" className="text-xs font-medium text-primary hover:underline">Relationships →</Link>}>
            {data.requests.length ? <ul className="divide-y text-sm">{data.requests.map((r) => (
              <li key={r.id} className="flex items-start justify-between gap-2 py-2"><div className="min-w-0"><div className="font-medium">{r.provider}</div>
                <div className="text-xs text-muted-foreground">{r.subject} · opened {fmtDate(r.opened_at, false)}</div></div><StatusPill status={r.status} /></li>))}</ul>
              : <Empty>No requests yet.</Empty>}
          </Section>
        </div>
      </div>

      <Section title="Plants in this country" actions={<Link href="/coverage" className="text-xs font-medium text-primary hover:underline">All plants →</Link>}>
        {data.plants.length ? <div className="-mx-4 -my-4 overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="py-2 pr-3 pl-4 font-medium">Plant</th>
            <th className="pr-3 font-medium">Customer</th><th className="pr-3 text-right font-medium">MW</th>
            {NEEDS.map((n) => <th key={n} className="pr-3 font-medium">{NEED_LABEL[n]}</th>)}</tr></thead>
          <tbody>{data.plants.map((a) => (
            <tr key={a.asset_id} className="border-b last:border-0"><td className="py-2 pr-3 pl-4">{a.name}<div className="text-xs text-muted-foreground">{a.bidding_zone}</div></td>
              <td className="pr-3 text-xs">{a.customer}</td><td className="pr-3 text-right tabular-nums">{a.capacity_mw}</td>
              {NEEDS.map((n) => { const i = a.needs.find((x) => x.need === n); return <td key={n} className="pr-3">{i ? <CoverageChip status={i.status} title={i.reason} /> : <span className="text-xs text-muted-foreground">—</span>}</td>; })}
            </tr>))}</tbody></table></div> : <Empty>No customer plants in this country yet.</Empty>}
      </Section>
    </div>
  );
}

function RouteCard({ r, onPatch }: { r: AccessRoute; onPatch: (path: string, body: unknown, ok?: string) => void }) {
  return (
    <div className={cn("rounded-lg border p-3 text-sm", r.is_fallback && "border-dashed", r.status === "blocked" && "border-orange-300 dark:border-orange-900")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-medium">{r.holder_name}{r.is_fallback && <span className="ml-1.5 text-xs font-normal text-muted-foreground">(fallback)</span>}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            {humanise(r.route_type)} · effort {r.effort ?? "?"}{r.requires_owner_authorisation && <span className="inline-flex items-center gap-0.5"><KeyRound className="size-3" />owner authorisation</span>}
            <EvidenceBadge level={r.evidence_level} />
            {r.source_url && <a href={r.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-primary hover:underline">source<ExternalLink className="size-3" /></a>}
          </div>
        </div>
        <NativeSelect value={r.status} aria-label="Route status" className="h-7 shrink-0 text-xs" onChange={(e) => onPatch(`/routes/${r.id}`, { status: e.target.value }, "Route updated")}>
          {ROUTE_STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}</NativeSelect>
      </div>
      {r.blockers && <div className="mt-2 rounded bg-orange-50 px-2 py-1 text-xs text-orange-900 dark:bg-orange-950 dark:text-orange-200">Blocker: {r.blockers}</div>}
      {r.notes && <div className="mt-1.5 text-xs text-muted-foreground">{r.notes}</div>}
    </div>
  );
}

function AddRoute({ country, onAdded }: { country: string; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const init = { data_need: "production_metering", holder_name: "", route_type: "authorised_api", is_fallback: false, effort: "medium",
    requires_owner_authorisation: false, blockers: "", evidence_level: "assumption", source_url: "" };
  const [f, setF] = useState(init);
  if (!open) return <Button variant="outline" size="sm" className="mt-4" onClick={() => setOpen(true)}><Plus />Add route</Button>;
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`/countries/${country}/routes`, { method: "POST", json: { ...f, blockers: f.blockers || null, source_url: f.source_url || null } });
      toast.success("Route added"); setF(init); setOpen(false); onAdded();
    } catch (err) { toast.error((err as Error).message); }
  }
  return (
    <form onSubmit={submit} className="mt-4 grid gap-2 rounded-lg border bg-muted/40 p-3 md:grid-cols-4">
      <Field label="Data need"><NativeSelect value={f.data_need} onChange={(e) => setF({ ...f, data_need: e.target.value })}>{NEEDS.map((n) => <option key={n} value={n}>{NEED_LABEL[n]}</option>)}</NativeSelect></Field>
      <Field label="Data holder *"><Input required value={f.holder_name} onChange={(e) => setF({ ...f, holder_name: e.target.value })} /></Field>
      <Field label="Route type"><NativeSelect value={f.route_type} onChange={(e) => setF({ ...f, route_type: e.target.value })}>
        {["public_api", "authorised_api", "public_download", "portal_export", "file_delivery", "email_request", "third_party"].map((t) => <option key={t} value={t}>{humanise(t)}</option>)}</NativeSelect></Field>
      <Field label="Evidence"><NativeSelect value={f.evidence_level} onChange={(e) => setF({ ...f, evidence_level: e.target.value })}>
        <option value="verified">Verified</option><option value="researched">Researched</option><option value="assumption">Assumption</option></NativeSelect></Field>
      <Field label="Blockers" className="md:col-span-2"><Input value={f.blockers} onChange={(e) => setF({ ...f, blockers: e.target.value })} /></Field>
      <Field label="Source URL"><Input type="url" value={f.source_url} onChange={(e) => setF({ ...f, source_url: e.target.value })} /></Field>
      <div className="flex items-end gap-3 text-sm">
        <label className="flex items-center gap-1"><input type="checkbox" checked={f.is_fallback} onChange={(e) => setF({ ...f, is_fallback: e.target.checked })} />Fallback</label>
        <label className="flex items-center gap-1"><input type="checkbox" checked={f.requires_owner_authorisation} onChange={(e) => setF({ ...f, requires_owner_authorisation: e.target.checked })} />Owner auth</label>
      </div>
      <div className="flex gap-2 md:col-span-4"><Button type="submit" size="sm">Save route</Button><Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button></div>
    </form>
  );
}

function Lessons({ country, initial, onSaved }: { country: string; initial: string; onSaved: () => void }) {
  const [v, setV] = useState(initial);
  async function save() {
    try { await api(`/countries/${country}`, { method: "PATCH", json: { lessons_learned: v } }); toast.success("Lessons saved"); onSaved(); }
    catch (e) { toast.error((e as Error).message); }
  }
  return (
    <Section title="Lessons learned" description="What the next country should reuse — this is how each connection gets easier."
      actions={<Button size="sm" variant="secondary" disabled={v === initial} onClick={save}>Save</Button>}>
      <Textarea rows={6} value={v} onChange={(e) => setV(e.target.value)} placeholder="- What surprised us…" />
    </Section>
  );
}
