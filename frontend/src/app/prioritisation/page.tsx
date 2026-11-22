"use client";
import { useState } from "react";
import { Info, Plus, Save } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import type { Opportunity, Page, Provider, Weights } from "@/lib/types";
import { fmtNum, humanise } from "@/lib/format";
import { Empty, ErrorState, Loading, PageHeader, Section } from "@/components/gridlink/page";
import { Field, NativeSelect } from "@/components/gridlink/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const BENEFITS = [["customer_value", "Customer value", "CV"], ["data_importance", "Data importance", "DI"],
  ["strategic_relevance", "Strategic relevance", "SR"], ["commercial_opportunity", "Commercial opportunity", "CO"]] as const;
const COSTS = [["technical_effort", "Technical effort", "TE"], ["access_complexity", "Access complexity", "AC"]] as const;
const FACTORS = [...BENEFITS, ...COSTS];
type FactorKey = (typeof FACTORS)[number][0];
const DECISIONS = ["proposed", "approved", "in_progress", "deferred", "rejected", "done"];

interface Listing { items: Opportunity[]; weights: Weights; disclaimer: string; formula: string }

export default function PrioritisationPage() {
  const { data, error, loading, reload } = useApi<Listing>("/integration-opportunities");
  const providers = useApi<Page<Provider>>("/providers?limit=200");
  const [draft, setWeights] = useState<Weights | null>(null);
  const [selected, setSelected] = useState<Opportunity | null>(null);
  const [compare, setCompare] = useState<number[]>([]);
  const [adding, setAdding] = useState(false);
  const weights = draft ?? data?.weights ?? null;

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data || !weights) return <Loading />;

  async function patch(o: Opportunity, body: Partial<Opportunity>) {
    try {
      await api(`/integration-opportunities/${o.id}`, { method: "PATCH", json: body });
      reload();
    } catch (e) { toast.error((e as Error).message); }
  }
  async function saveWeights() {
    try {
      await api("/prioritisation/weights", { method: "PUT", json: weights });
      toast.success("Weights saved — all priority scores recalculated");
      setWeights(null);
      reload();
    } catch (e) { toast.error((e as Error).message); }
  }
  const compared = data.items.filter((o) => compare.includes(o.id));

  return (
    <div className="space-y-6">
      <PageHeader title="Connection prioritisation"
        description="Rank potential provider integrations with a transparent, editable model. Change any score and the ranking updates immediately."
        actions={<Button onClick={() => setAdding(true)}><Plus />Add opportunity</Button>} />

      <div className="flex items-start gap-2 rounded-xl border bg-muted/50 p-3 text-sm">
        <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <div><strong>Product-planning framework.</strong> {data.disclaimer}</div>
      </div>

      <Section title="Scoring model" description="Each factor is scored 1–5 and normalised to score ÷ 5 (0.2–1.0). Weights are exponents: 0 removes a factor, 2 doubles its influence."
        actions={<Button size="sm" variant="secondary" onClick={saveWeights}><Save />Save weights</Button>}>
        <div className="mb-4 rounded-lg bg-muted px-4 py-3 text-center font-mono text-sm">
          Priority = ({BENEFITS.filter(([k]) => weights[k] > 0).map(([k, , a]) => weights[k] === 1 ? a : `${a}^${weights[k]}`).join(" × ") || "1"})
          {" ÷ "}({COSTS.filter(([k]) => weights[k] > 0).map(([k, , a]) => weights[k] === 1 ? a : `${a}^${weights[k]}`).join(" × ") || "1"})
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {FACTORS.map(([k, label, abbr]) => (
            <Field key={k} label={`${label} (${abbr})`} hint={COSTS.some(([c]) => c === k) ? "Cost factor — divides" : "Benefit factor — multiplies"}>
              <Input type="number" min={0} max={3} step={0.5} value={weights[k]} onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) })} />
            </Field>
          ))}
        </div>
      </Section>

      <Section title="Ranked integrations" description="Click a row to document rationale and the decision. Tick rows to compare.">
        {!data.items.length ? <Empty>No opportunities yet.</Empty> : (
          <div className="-mx-4 -my-4 overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead className="w-8 pl-4" /><TableHead>Rank</TableHead><TableHead>Opportunity</TableHead>
                {FACTORS.map(([k, , a]) => <TableHead key={k} className="text-center" title={humanise(k)}>{a}</TableHead>)}
                <TableHead className="text-right">Weeks</TableHead><TableHead className="text-right">Score</TableHead><TableHead className="pr-4">Decision</TableHead>
              </TableRow></TableHeader>
              <TableBody>{data.items.map((o) => (
                <TableRow key={o.id} className="cursor-pointer" onClick={() => setSelected(o)}>
                  <TableCell className="pl-4" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" aria-label={`Compare ${o.title}`} checked={compare.includes(o.id)}
                      onChange={(e) => setCompare(e.target.checked ? [...compare, o.id] : compare.filter((x) => x !== o.id))} /></TableCell>
                  <TableCell className="font-semibold tabular-nums">{o.rank}</TableCell>
                  <TableCell><div className="font-medium">{o.title}</div><div className="text-xs text-muted-foreground">{o.provider_name} · {o.country_code}</div></TableCell>
                  {FACTORS.map(([k]) => (
                    <TableCell key={k} className="text-center" onClick={(e) => e.stopPropagation()}>
                      <NativeSelect aria-label={humanise(k)} value={o[k as FactorKey]} className="h-7 w-12 px-1 text-center"
                        onChange={(e) => patch(o, { [k]: Number(e.target.value) } as Partial<Opportunity>)}>
                        {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}</NativeSelect>
                    </TableCell>
                  ))}
                  <TableCell className="text-right tabular-nums">{o.estimated_weeks ?? "—"}</TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">{fmtNum(o.priority_score, 2)}</TableCell>
                  <TableCell className="pr-4 text-xs">{humanise(o.decision_status)}</TableCell>
                </TableRow>
              ))}</TableBody>
            </Table>
          </div>
        )}
      </Section>

      {compared.length >= 2 && (
        <Section title="Comparison" description="Normalised factor values side by side.">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="py-2 pr-4 font-medium">Factor</th>
                {compared.map((o) => <th key={o.id} className="pr-4 font-medium">#{o.rank} {o.title}</th>)}</tr></thead>
              <tbody>
                {FACTORS.map(([k, label]) => (
                  <tr key={k} className="border-b">
                    <td className="py-1.5 pr-4 text-xs">{label}{weights[k] === 0 && <span className="text-muted-foreground"> (weight 0)</span>}</td>
                    {compared.map((o) => {
                      const v = o[k as FactorKey] / 5;
                      return <td key={o.id} className="pr-4"><div className="flex items-center gap-2">
                        <div className="h-2 w-28 rounded bg-muted"><div className={`h-2 rounded ${COSTS.some(([c]) => c === k) ? "bg-orange-500" : "bg-primary"}`} style={{ width: `${v * 100}%` }} /></div>
                        <span className="text-xs tabular-nums">{v.toFixed(1)}</span></div></td>;
                    })}
                  </tr>
                ))}
                <tr><td className="py-2 pr-4 text-xs font-medium">Priority score</td>{compared.map((o) => <td key={o.id} className="pr-4 font-semibold tabular-nums">{fmtNum(o.priority_score, 2)}</td>)}</tr>
                <tr><td className="py-1 pr-4 align-top text-xs font-medium">Rationale</td>{compared.map((o) => <td key={o.id} className="pr-4 align-top text-xs text-muted-foreground">{o.rationale ?? "—"}</td>)}</tr>
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {selected && <DecisionDialog o={selected} onClose={() => setSelected(null)} onSaved={reload} />}
      <AddDialog open={adding} onOpenChange={setAdding} providers={providers.data?.items ?? []} onSaved={reload} />
    </div>
  );
}

function DecisionDialog({ o, onClose, onSaved }: { o: Opportunity; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ rationale: o.rationale ?? "", decision_status: o.decision_status, decision_notes: o.decision_notes ?? "",
    estimated_weeks: o.estimated_weeks ?? "" });
  async function save() {
    try {
      await api(`/integration-opportunities/${o.id}`, { method: "PATCH", json: { ...f, estimated_weeks: f.estimated_weeks === "" ? null : Number(f.estimated_weeks) } });
      toast.success("Decision documented");
      onSaved(); onClose();
    } catch (e) { toast.error((e as Error).message); }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>{o.title}</DialogTitle>
          <DialogDescription>{o.provider_name} · rank #{o.rank} · score {fmtNum(o.priority_score, 2)}</DialogDescription></DialogHeader>
        <div className="space-y-3">
          <Field label="Rationale"><Textarea rows={3} value={f.rationale} onChange={(e) => setF({ ...f, rationale: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Decision"><NativeSelect value={f.decision_status} onChange={(e) => setF({ ...f, decision_status: e.target.value })}>
              {DECISIONS.map((d) => <option key={d} value={d}>{humanise(d)}</option>)}</NativeSelect></Field>
            <Field label="Estimated weeks"><Input type="number" min={0} step={0.5} value={f.estimated_weeks} onChange={(e) => setF({ ...f, estimated_weeks: e.target.value })} /></Field>
          </div>
          <Field label="Decision notes" hint="Who decided, when, and what would change the decision."><Textarea rows={3} value={f.decision_notes} onChange={(e) => setF({ ...f, decision_notes: e.target.value })} /></Field>
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={save}>Save decision</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AddDialog({ open, onOpenChange, providers, onSaved }: { open: boolean; onOpenChange: (o: boolean) => void; providers: Provider[]; onSaved: () => void }) {
  const init = { provider_id: "", title: "", customer_value: 3, data_importance: 3, commercial_opportunity: 3, strategic_relevance: 3,
    technical_effort: 3, access_complexity: 3, estimated_weeks: "", rationale: "" };
  const [f, setF] = useState(init);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/integration-opportunities", { method: "POST", json: { ...f, provider_id: Number(f.provider_id),
        estimated_weeks: f.estimated_weeks === "" ? null : Number(f.estimated_weeks) } });
      toast.success("Opportunity added and scored");
      setF(init); onOpenChange(false); onSaved();
    } catch (err) { toast.error((err as Error).message); }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader><DialogTitle>Add integration opportunity</DialogTitle>
          <DialogDescription>Score each factor 1 (low) to 5 (high). For cost factors, 5 means the most effort / most complex access.</DialogDescription></DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Provider *"><NativeSelect required value={f.provider_id} onChange={(e) => setF({ ...f, provider_id: e.target.value })}>
              <option value="">Select…</option>{providers.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.country_code})</option>)}</NativeSelect></Field>
            <Field label="Title *"><Input required minLength={3} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {FACTORS.map(([k, label]) => (
              <Field key={k} label={label}><NativeSelect value={f[k]} onChange={(e) => setF({ ...f, [k]: Number(e.target.value) })}>
                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}</NativeSelect></Field>
            ))}
          </div>
          <Field label="Estimated implementation (weeks)"><Input type="number" min={0} step={0.5} value={f.estimated_weeks} onChange={(e) => setF({ ...f, estimated_weeks: e.target.value })} /></Field>
          <Field label="Rationale"><Textarea rows={2} value={f.rationale} onChange={(e) => setF({ ...f, rationale: e.target.value })} /></Field>
          <DialogFooter><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit">Add</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
