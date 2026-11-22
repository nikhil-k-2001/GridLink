"use client";
import { useState } from "react";
import { Loader2, Play, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import type { ApiTest, Page, Provider } from "@/lib/types";
import { fmtDate, fmtNum } from "@/lib/format";
import { Empty, Loading, PageHeader, Section } from "@/components/gridlink/page";
import { StatusPill } from "@/components/gridlink/coverage";
import { Field, NativeSelect } from "@/components/gridlink/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type KVRow = { k: string; v: string };
interface Preset { label: string; provider: string; name: string; url: string; params: KVRow[]; headers: KVRow[]; note: string }

const PRESETS: Preset[] = [
  { label: "ENTSO-E prices without a token", provider: "ENTSO-E", name: "ENTSO-E A44 — no token", url: "https://web-api.tp.entsoe.eu/api",
    params: [{ k: "documentType", v: "A44" }, { k: "in_Domain", v: "10YFR-RTE------C" }, { k: "out_Domain", v: "10YFR-RTE------C" },
      { k: "periodStart", v: "202611200000" }, { k: "periodEnd", v: "202611210000" }], headers: [],
    note: "Real call. Expect HTTP 401 — proves the token requirement." },
  { label: "SMARD price CSV (real)", provider: "SMARD", name: "SMARD DE-LU quarter-hour prices", url: "https://www.smard.de/app/chart_data/4169/DE/index_quarterhour.json",
    params: [], headers: [], note: "Real public endpoint: list of available weekly files for DE-LU prices." },
  { label: "MaStR bulk-download page (real)", provider: "Marktstamm", name: "MaStR Datendownload page", url: "https://www.marktstammdatenregister.de/MaStR/Datendownload",
    params: [], headers: [], note: "Real page: confirm the daily export exists and its date." },
  { label: "France DSO — consent granted (simulated)", provider: "Enedis", name: "FR DSO load curve — Plaine de Beauce",
    url: "http://localhost:8000/simulated/fr-dso/v5/metering_data/production_load_curve",
    params: [{ k: "usage_point_id", v: "99000000000101" }, { k: "start", v: "2026-11-18" }, { k: "end", v: "2026-11-19" }],
    headers: [{ k: "Authorization", v: "Bearer sim-fr-oauth-token" }], note: "Simulated platform. 30-min W, interval-end Paris time." },
  { label: "France DSO — consent revoked (simulated)", provider: "Enedis", name: "FR DSO load curve — Provence Solar II",
    url: "http://localhost:8000/simulated/fr-dso/v5/metering_data/production_load_curve",
    params: [{ k: "usage_point_id", v: "99000000000104" }, { k: "start", v: "2026-11-18" }, { k: "end", v: "2026-11-19" }],
    headers: [{ k: "Authorization", v: "Bearer sim-fr-oauth-token" }], note: "Simulated. Expect 403: the owner revoked consent at the DSO." },
  { label: "Spain DSO — hourly kWh (simulated)", provider: "Datadis", name: "ES DSO production — Extremadura Solar",
    url: "http://localhost:8000/simulated/es-dso/api-private/api/get-production-data",
    params: [{ k: "cups", v: "ES0000SIM0000000202ZZ" }, { k: "startDate", v: "2026/11/18" }, { k: "endDate", v: "2026/11/18" }],
    headers: [{ k: "Authorization", v: "Bearer sim-es-token" }], note: "Simulated. Hour-ending labels incl. '24:00'; some values 'Estimada'." },
];

function KVEditor({ rows, onChange, label }: { rows: KVRow[]; onChange: (r: KVRow[]) => void; label: string }) {
  return (
    <div className="space-y-1.5">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      {rows.map((r, i) => (
        <div key={i} className="flex gap-1.5">
          <Input className="font-mono text-xs" placeholder="name" value={r.k} onChange={(e) => onChange(rows.map((x, j) => j === i ? { ...x, k: e.target.value } : x))} />
          <Input className="font-mono text-xs" placeholder="value" value={r.v} onChange={(e) => onChange(rows.map((x, j) => j === i ? { ...x, v: e.target.value } : x))} />
          <Button type="button" size="icon" variant="ghost" aria-label="Remove" onClick={() => onChange(rows.filter((_, j) => j !== i))}><Trash2 /></Button>
        </div>))}
      <Button type="button" size="xs" variant="ghost" onClick={() => onChange([...rows, { k: "", v: "" }])}><Plus />Add</Button>
    </div>
  );
}

const toObj = (rows: KVRow[]) => Object.fromEntries(rows.filter((r) => r.k.trim()).map((r) => [r.k.trim(), r.v]));

export default function ApiBenchPage() {
  const providers = useApi<Page<Provider>>("/providers?limit=200");
  const history = useApi<ApiTest[]>("/api-tests");
  const allow = useApi<{ hosts: string[] }>("/api-tests/allowlist");
  const [f, setF] = useState({ name: "", provider_id: "", method: "GET", url: "", params: [] as KVRow[], headers: [] as KVRow[], body: "" });
  const [note, setNote] = useState("");
  const [presetProvider, setPresetProvider] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ApiTest | null>(null);

  function preset(p: Preset) {
    const prov = providers.data?.items.find((x) => x.name.includes(p.provider));
    setF({ name: p.name, provider_id: prov ? String(prov.id) : "", method: "GET", url: p.url, params: p.params, headers: p.headers, body: "" });
    setNote(p.note);
    setPresetProvider(p.provider);
  }
  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      // providers may still be loading when a preset is picked: resolve by name at send time
      const pid = f.provider_id || (presetProvider ? String(providers.data?.items.find((x) => x.name.includes(presetProvider))?.id ?? "") : "");
      const t = await api<ApiTest>("/api-tests/run", { method: "POST", json: { name: f.name || f.url, provider_id: pid ? Number(pid) : null,
        method: f.method, url: f.url, params: toObj(f.params), headers: toObj(f.headers), body: f.body || null } });
      setResult(t); history.reload();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="API test bench"
        description="Test a provider's API before engineering commits time: make the request, inspect the response, record a verdict, and promote what you learned to a verified fact on the provider. Secrets are redacted before anything is stored." />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Section title="Request">
          <div className="mb-3 flex flex-wrap gap-1.5">{PRESETS.map((p) => <Button key={p.label} size="xs" variant="outline" onClick={() => preset(p)}>{p.label}</Button>)}</div>
          {note && <p className="mb-3 rounded-md bg-muted px-2 py-1.5 text-xs text-muted-foreground">{note}</p>}
          <form onSubmit={run} className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <Field label="Test name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
              <Field label="Provider"><NativeSelect value={f.provider_id} onChange={(e) => { setPresetProvider(""); setF({ ...f, provider_id: e.target.value }); }}>
                <option value="">—</option>{providers.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</NativeSelect></Field>
            </div>
            <div className="flex gap-2">
              <NativeSelect value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })} aria-label="Method"><option>GET</option><option>POST</option></NativeSelect>
              <Input required className="font-mono text-xs" placeholder="https://…" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} />
            </div>
            <KVEditor label="Query parameters" rows={f.params} onChange={(params) => setF({ ...f, params })} />
            <KVEditor label="Headers (values of auth headers are redacted when stored)" rows={f.headers} onChange={(headers) => setF({ ...f, headers })} />
            {f.method === "POST" && <Field label="Body"><Textarea rows={4} className="font-mono text-xs" value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></Field>}
            <Button type="submit" disabled={busy || !f.url}>{busy ? <Loader2 className="animate-spin" /> : <Play />}Send request</Button>
            <p className="text-[11px] text-muted-foreground">Allowed hosts: {allow.data?.hosts.join(", ")} and the simulated DSO platforms on localhost.</p>
          </form>
        </Section>
        <Section title="Response">{result ? <ResultView key={result.id} t={result} onSaved={history.reload} /> : <Empty>Pick a preset or enter a request, then send it.</Empty>}</Section>
      </div>

      <Section title="Evidence log" description="Every test is kept with its redacted request, so findings in onboarding reports can be traced back.">
        {!history.data ? <Loading /> : !history.data.length ? <Empty>No tests yet.</Empty> : (
          <ul className="divide-y text-sm">{history.data.map((t) => (
            <li key={t.id}><button onClick={() => setResult(t)} className="flex w-full items-center justify-between gap-3 py-2 text-left hover:bg-muted/40">
              <div className="min-w-0"><div className="truncate font-medium">{t.name}</div>
                <div className="truncate font-mono text-[11px] text-muted-foreground">{t.method} {t.url}</div>
                <div className="text-xs text-muted-foreground">{t.provider ?? "No provider"} · {fmtDate(t.created_at)}{t.notes ? ` · ${t.notes}` : ""}</div></div>
              <div className="flex shrink-0 items-center gap-2"><code className="text-xs">{t.status_code ?? "ERR"}</code><Verdict v={t.verdict} /></div>
            </button></li>))}</ul>)}
      </Section>
    </div>
  );
}

function Verdict({ v }: { v: string }) {
  const map: Record<string, string> = { works: "done", partial: "in_progress", fails: "blocked", inconclusive: "draft" };
  return <StatusPill status={map[v] ?? v} className="capitalize" />;
}

function ResultView({ t, onSaved }: { t: ApiTest; onSaved: () => void }) {
  const [verdict, setVerdict] = useState(t.verdict);
  const [notes, setNotes] = useState(t.notes ?? "");
  const [fact, setFact] = useState("");
  async function save() {
    try { await api(`/api-tests/${t.id}`, { method: "PATCH", json: { verdict, notes } }); toast.success("Verdict saved"); onSaved(); }
    catch (e) { toast.error((e as Error).message); }
  }
  async function promote() {
    try { await api(`/api-tests/${t.id}/promote`, { method: "POST", json: { statement: fact, category: "access" } });
      toast.success("Recorded as a verified fact on the provider"); setFact(""); }
    catch (e) { toast.error((e as Error).message); }
  }
  const ok = t.status_code !== null && t.status_code < 300;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className={cn("rounded-md px-2 py-0.5 font-mono font-semibold", ok ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" : "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300")}>
          {t.status_code ?? "ERROR"}</span>
        <span className="text-muted-foreground">{t.duration_ms} ms · {fmtNum((t.response_size ?? 0) / 1024, 1)} KB · {t.content_type ?? "—"}</span>
      </div>
      {t.error && <p className="text-sm text-red-700">{t.error}</p>}
      <div className="text-xs"><span className="text-muted-foreground">Stored request headers: </span><code>{JSON.stringify(t.request_headers)}</code></div>
      {Object.keys(t.response_headers).length > 0 && <div className="text-xs"><span className="text-muted-foreground">Response headers: </span><code>{JSON.stringify(t.response_headers)}</code></div>}
      <pre className="max-h-96 overflow-auto rounded-lg bg-muted p-3 text-[11px] leading-relaxed">{t.response_excerpt ?? ""}</pre>
      <div className="grid gap-2 md:grid-cols-[140px_1fr_auto]">
        <NativeSelect value={verdict} onChange={(e) => setVerdict(e.target.value)} aria-label="Verdict">
          {["works", "partial", "fails", "inconclusive"].map((v) => <option key={v} value={v}>{v}</option>)}</NativeSelect>
        <Input placeholder="What did we learn?" value={notes} onChange={(e) => setNotes(e.target.value)} />
        <Button variant="secondary" onClick={save}>Save verdict</Button>
      </div>
      {t.provider_id && (
        <div className="flex gap-2 rounded-lg border border-dashed p-2">
          <Input placeholder="Verified fact, e.g. 'Returns HTTP 401 without a security token'" value={fact} onChange={(e) => setFact(e.target.value)} />
          <Button variant="outline" disabled={fact.length < 5} onClick={promote}><ShieldCheck />Record as verified fact</Button>
        </div>)}
    </div>
  );
}
