"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { api, qs } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import type { Issue } from "@/lib/types";
import { fmtDate, humanise, relTime } from "@/lib/format";
import { Empty, ErrorState, KV, Loading, PageHeader, Section } from "@/components/gridlink/page";
import { SeverityBadge, StatusPill } from "@/components/gridlink/coverage";
import { Field, NativeSelect } from "@/components/gridlink/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const STATUSES = ["open", "investigating", "waiting_on_provider", "resolved"];

export default function IssuesPage() {
  return <Suspense fallback={<Loading />}><Issues /></Suspense>;
}

function Issues() {
  const params = useSearchParams();
  const router = useRouter();
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const { data, error, loading, reload } = useApi<Issue[]>(`/issues${qs({ status, severity })}`);
  const [creating, setCreating] = useState(false);
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading && !data) return <Loading />;
  const items = data ?? [];
  const selected = items.find((i) => String(i.id) === params.get("id")) ?? items.find((i) => i.status !== "resolved") ?? items[0];

  return (
    <div className="space-y-5">
      <PageHeader title="Data issues"
        description="Incomplete, late or refused data, traced to the plants and customers it affects. Issues are raised automatically at ingestion; a person owns each one until the root cause, customer update and resolution are written down."
        actions={<Button onClick={() => setCreating(!creating)}><Plus />Log issue</Button>} />
      {creating && <NewIssue onSaved={() => { setCreating(false); reload(); }} />}
      <div className="flex flex-wrap gap-2">
        <NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">All statuses</option>{STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}</NativeSelect>
        <NativeSelect value={severity} onChange={(e) => setSeverity(e.target.value)} aria-label="Severity">
          <option value="">All severities</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></NativeSelect>
        <span className="self-center text-xs text-muted-foreground">{items.length} issues</span>
      </div>
      {!items.length ? <Empty>No issues match.</Empty> : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <ul className="space-y-2">{items.map((i) => (
            <li key={i.id}>
              <button onClick={() => router.replace(`/issues?id=${i.id}`)}
                className={cn("w-full rounded-lg border bg-card p-3 text-left transition-colors hover:bg-muted/50", selected?.id === i.id && "border-primary ring-1 ring-primary", i.status === "resolved" && "opacity-60")}>
                <div className="flex items-start justify-between gap-2"><span className="line-clamp-2 text-sm font-medium">{i.title}</span><SeverityBadge severity={i.severity} /></div>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground"><StatusPill status={i.status} />
                  <span>{i.source === "auto" ? "auto-detected" : "logged manually"} · {relTime(i.detected_at)}</span>
                  {i.affected_mw > 0 && <span>· {i.affected_mw} MW</span>}</div>
              </button>
            </li>))}</ul>
          {selected && <IssueDetail key={`${selected.id}-${selected.updated_at}`} issue={selected} onSaved={reload} />}
        </div>
      )}
    </div>
  );
}

function IssueDetail({ issue, onSaved }: { issue: Issue; onSaved: () => void }) {
  const [f, setF] = useState({ status: issue.status, hypotheses: issue.hypotheses ?? "", root_cause: issue.root_cause ?? "",
    provider_contacted: issue.provider_contacted, customer_update: issue.customer_update ?? "", resolution: issue.resolution ?? "" });
  async function save() {
    try { await api(`/issues/${issue.id}`, { method: "PATCH", json: f }); toast.success("Issue updated"); onSaved(); }
    catch (e) { toast.error((e as Error).message); }
  }
  const series = (issue.evidence?.series ?? {}) as Record<string, { completeness: number; missing_periods: { start: string; end: string; intervals: number }[] }>;
  return (
    <Section title={issue.title} description={<>#{issue.id} · <code>{issue.code}</code> · detected {fmtDate(issue.detected_at)}{issue.resolved_at ? ` · resolved ${fmtDate(issue.resolved_at)}` : ""}</>}
      actions={<SeverityBadge severity={issue.severity} />}>
      <div className="space-y-4">
        <KV items={[
          ["Connector", issue.connector_id ? <Link key="c" href={`/connectors/${issue.connector_id}`} className="text-primary hover:underline">{issue.connector}</Link> : "—"],
          ["Provider", issue.provider ?? "—"],
          ["Customers affected", issue.affected_customers.join(", ") || "None at plant level"],
          ["Plants affected", issue.affected_assets.map((a) => `${a.name} (${a.capacity_mw} MW)`).join(", ") || "—"],
          ["Period", issue.period_start ? `${fmtDate(issue.period_start)} → ${fmtDate(issue.period_end)}` : "—"],
          ["Seen in syncs", ((issue.evidence?.syncs as number[]) ?? []).map((s) => `#${s}`).join(", ") || "—"],
        ]} />
        {Object.keys(series).length > 0 && (
          <div className="rounded-lg bg-muted/50 p-3 text-xs"><div className="mb-1 font-medium">Evidence: missing data</div>
            {Object.entries(series).map(([k, v]) => <div key={k}><code>{k}</code> {v.completeness}% complete
              {v.missing_periods.slice(0, 2).map((p) => <span key={p.start} className="text-muted-foreground"> · {fmtDate(p.start)} → {fmtDate(p.end)} ({p.intervals} intervals)</span>)}</div>)}</div>
        )}
        {Boolean(issue.evidence?.responses) && (
          <div className="rounded-lg bg-muted/50 p-3 text-xs"><div className="mb-1 font-medium">Evidence: provider responses</div>
            <pre className="overflow-x-auto whitespace-pre-wrap">{JSON.stringify(issue.evidence.responses, null, 2)}</pre></div>)}
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Status"><NativeSelect value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
            {STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}</NativeSelect></Field>
          <label className="flex items-end gap-2 pb-1 text-sm"><input type="checkbox" checked={f.provider_contacted} onChange={(e) => setF({ ...f, provider_contacted: e.target.checked })} />Provider contacted</label>
          <Field label="Hypotheses (competing explanations)" className="md:col-span-2"><Textarea rows={3} value={f.hypotheses} onChange={(e) => setF({ ...f, hypotheses: e.target.value })} /></Field>
          <Field label="Root cause (confirmed)" className="md:col-span-2"><Textarea rows={2} value={f.root_cause} onChange={(e) => setF({ ...f, root_cause: e.target.value })} /></Field>
          <Field label="Customer update (for Customer Operations)" className="md:col-span-2"><Textarea rows={2} value={f.customer_update} onChange={(e) => setF({ ...f, customer_update: e.target.value })} /></Field>
          <Field label="Resolution (required to close)" className="md:col-span-2"><Textarea rows={2} value={f.resolution} onChange={(e) => setF({ ...f, resolution: e.target.value })} /></Field>
        </div>
        <Button onClick={save}>Save</Button>
      </div>
    </Section>
  );
}

function NewIssue({ onSaved }: { onSaved: () => void }) {
  const [f, setF] = useState({ title: "", severity: "medium", hypotheses: "" });
  async function save(e: React.FormEvent) {
    e.preventDefault();
    try { await api("/issues", { method: "POST", json: f }); toast.success("Issue logged"); onSaved(); }
    catch (err) { toast.error((err as Error).message); }
  }
  return (
    <form onSubmit={save} className="grid gap-2 rounded-xl border bg-card p-3 md:grid-cols-[1fr_140px]">
      <Field label="Title *"><Input required minLength={3} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="e.g. Customer reports missing October data for Puglia Solar" /></Field>
      <Field label="Severity"><NativeSelect value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })}><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></NativeSelect></Field>
      <Field label="Hypotheses" className="md:col-span-2"><Textarea rows={2} value={f.hypotheses} onChange={(e) => setF({ ...f, hypotheses: e.target.value })} /></Field>
      <div><Button type="submit" size="sm">Log issue</Button></div>
    </form>
  );
}
