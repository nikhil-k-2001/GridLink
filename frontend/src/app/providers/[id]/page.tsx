"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ExternalLink, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { PROVIDER_STATUSES, type Connector, type EvidenceLevel, type Investigation, type Page, type ProviderDetail } from "@/lib/types";
import { fmtDate, humanise } from "@/lib/format";
import { Empty, ErrorState, KV, Loading, PageHeader, Section } from "@/components/gridlink/page";
import { EvidenceBadge, HealthBadge, OriginBadge, ProviderStatusBadge } from "@/components/gridlink/status";
import { Field, NativeSelect } from "@/components/gridlink/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const ext = (url: string | null) => url ? <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">{url.replace(/^https?:\/\//, "")}<ExternalLink className="size-3" /></a> : "—";

export default function ProviderPage() {
  const { id } = useParams<{ id: string }>();
  const { data: p, error, loading, reload } = useApi<ProviderDetail>(`/providers/${id}`);
  const connectors = useApi<Page<Connector>>(`/connectors?provider_id=${id}`);
  const investigations = useApi<Investigation[]>(`/investigations?provider_id=${id}`);

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !p) return <Loading />;
  const counts = { verified: 0, researched: 0, assumption: 0 } as Record<EvidenceLevel, number>;
  p.facts.forEach((f) => counts[f.evidence_level]++);
  const inv = investigations.data?.[0];

  return (
    <div className="space-y-6">
      <PageHeader title={p.name}
        description={<span className="flex flex-wrap items-center gap-2"><ProviderStatusBadge status={p.status} /><span className="font-mono text-xs">{p.country_code}</span>{p.description}</span>}
        actions={inv ? <Link href={`/documentation?investigation=${inv.id}`}><Button variant="outline">Onboarding report ({inv.completion}%)</Button></Link>
          : <Link href={`/documentation?provider=${p.id}`}><Button variant="outline">Start investigation</Button></Link>} />

      <div className="grid gap-6 xl:grid-cols-3">
        <Section title="Profile" className="xl:col-span-2">
          <KV items={[
            ["Website", ext(p.website)], ["API documentation", ext(p.documentation_url)],
            ["Authentication", p.authentication_type], ["Data formats", (p.data_formats ?? []).join(", ") || "—"],
            ["Access requirements", p.access_requirements], ["Registration status", p.registration_status],
            ["Licence", p.licence], ["Attribution", p.attribution],
            ["Last investigated", fmtDate(p.last_investigated_at, false)], ["Notes", p.notes],
          ]} />
        </Section>
        <WorkflowEditor key={p.updated_at} p={p} onSaved={reload} />
      </div>

      <Section title="Evidence register"
        description={`What we know and how strongly: ${counts.verified} verified · ${counts.researched} researched · ${counts.assumption} assumptions to confirm.`}>
        <FactList p={p} onChange={reload} />
      </Section>

      <div className="grid gap-6 xl:grid-cols-2">
        <Section title="Connectors">
          {connectors.data?.items.length ? (
            <ul className="divide-y text-sm">{connectors.data.items.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-2 py-2">
                <div className="min-w-0"><Link href={`/connectors/${c.id}`} className="font-medium hover:underline">{c.connector_name}</Link>
                  <div className="text-xs text-muted-foreground">{c.connector_type}</div></div>
                <div className="flex gap-1.5">{c.data_origin === "simulated" && <OriginBadge origin="simulated" />}{c.health && <HealthBadge status={c.health.status} />}</div>
              </li>))}</ul>
          ) : <Empty>No connector configured yet.</Empty>}
        </Section>
        <Section title="Datasets" description="Created from the provider mapping on first sync.">
          {p.datasets.length ? (
            <div className="-mx-4 -my-4 max-h-80 overflow-auto">
              <Table><TableHeader><TableRow><TableHead className="pl-4">Dataset</TableHead><TableHead>Metric</TableHead>
                <TableHead>Published unit</TableHead><TableHead className="pr-4">Frequency</TableHead></TableRow></TableHeader>
                <TableBody>{p.datasets.map((d) => (
                  <TableRow key={d.id} className={d.is_active ? "" : "opacity-50"}>
                    <TableCell className="pl-4 text-xs" title={d.description ?? ""}>{d.dataset_name}{!d.is_active && " (inactive)"}</TableCell>
                    <TableCell className="text-xs">{humanise(d.metric_type)}</TableCell>
                    <TableCell className="font-mono text-xs">{d.unit}</TableCell>
                    <TableCell className="pr-4 font-mono text-xs">{d.frequency}</TableCell>
                  </TableRow>))}</TableBody></Table>
            </div>
          ) : <Empty>No datasets yet.</Empty>}
        </Section>
      </div>
    </div>
  );
}

function WorkflowEditor({ p, onSaved }: { p: ProviderDetail; onSaved: () => void }) {
  const [f, setF] = useState({ status: p.status, owner: p.owner ?? "", next_action: p.next_action ?? "", registration_status: p.registration_status ?? "" });
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      await api(`/providers/${p.id}`, { method: "PATCH", json: { ...f, last_investigated_at: new Date().toISOString() } });
      toast.success("Provider workflow updated");
      onSaved();
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <Section title="Integration workflow">
      <div className="space-y-3">
        <Field label="Status"><NativeSelect value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as typeof f.status })}>
          {PROVIDER_STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}</NativeSelect></Field>
        <Field label="Assigned owner"><Input value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })} /></Field>
        <Field label="Registration status"><Input value={f.registration_status} onChange={(e) => setF({ ...f, registration_status: e.target.value })} /></Field>
        <Field label="Next action"><Textarea rows={3} value={f.next_action} onChange={(e) => setF({ ...f, next_action: e.target.value })} /></Field>
        <Button onClick={save} disabled={busy} className="w-full">{busy ? "Saving…" : "Save workflow"}</Button>
      </div>
    </Section>
  );
}

function FactList({ p, onChange }: { p: ProviderDetail; onChange: () => void }) {
  const [f, setF] = useState({ category: "access", statement: "", evidence_level: "assumption" as EvidenceLevel, source_url: "" });
  async function add(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`/providers/${p.id}/facts`, { method: "POST", json: { ...f, source_url: f.source_url || null } });
      setF({ ...f, statement: "", source_url: "" });
      onChange();
    } catch (err) { toast.error((err as Error).message); }
  }
  async function remove(id: number) {
    await api(`/providers/${p.id}/facts/${id}`, { method: "DELETE" }).then(onChange).catch((e: Error) => toast.error(e.message));
  }
  return (
    <div className="space-y-4">
      {p.facts.length ? (
        <ul className="divide-y text-sm">
          {p.facts.map((x) => (
            <li key={x.id} className="group flex items-start gap-3 py-2">
              <div className="w-24 shrink-0 pt-0.5"><EvidenceBadge level={x.evidence_level} /></div>
              <div className="w-24 shrink-0 pt-0.5 text-xs text-muted-foreground">{humanise(x.category)}</div>
              <div className="min-w-0 flex-1">{x.statement}
                {x.source_url && <a href={x.source_url} target="_blank" rel="noreferrer" className="ml-1.5 inline-flex items-center gap-0.5 text-xs text-primary hover:underline">source<ExternalLink className="size-3" /></a>}
                {x.checked_at && <span className="ml-1.5 text-xs text-muted-foreground">· checked {fmtDate(x.checked_at, false)}</span>}
              </div>
              <button aria-label="Remove fact" onClick={() => remove(x.id)} className="text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-red-600"><Trash2 className="size-4" /></button>
            </li>
          ))}
        </ul>
      ) : <Empty>No facts recorded.</Empty>}
      <form onSubmit={add} className="grid grid-cols-1 gap-2 rounded-lg border bg-muted/40 p-3 md:grid-cols-[120px_140px_1fr_200px_auto]">
        <NativeSelect value={f.evidence_level} onChange={(e) => setF({ ...f, evidence_level: e.target.value as EvidenceLevel })} aria-label="Evidence level">
          <option value="verified">Verified</option><option value="researched">Researched</option><option value="assumption">Assumption</option></NativeSelect>
        <NativeSelect value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} aria-label="Category">
          {["access", "format", "units", "time", "limits", "quality", "licensing", "stability", "documentation"].map((c) => <option key={c} value={c}>{humanise(c)}</option>)}</NativeSelect>
        <Input required placeholder="Statement, e.g. 'API returns HTTP 401 without token'" value={f.statement} onChange={(e) => setF({ ...f, statement: e.target.value })} />
        <Input type="url" placeholder="Source URL (optional)" value={f.source_url} onChange={(e) => setF({ ...f, source_url: e.target.value })} />
        <Button type="submit" variant="secondary"><Plus />Add fact</Button>
      </form>
    </div>
  );
}
