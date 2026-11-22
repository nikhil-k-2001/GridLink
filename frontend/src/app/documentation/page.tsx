"use client";
import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Download, FileText, Save } from "lucide-react";
import { toast } from "sonner";
import { API_URL, api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import type { Investigation, Page, Provider, TemplateSection } from "@/lib/types";
import { fmtDate } from "@/lib/format";
import { Empty, ErrorState, Loading, PageHeader, Section } from "@/components/gridlink/page";
import { ProviderStatusBadge } from "@/components/gridlink/status";
import { Field, NativeSelect } from "@/components/gridlink/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export default function DocumentationPage() {
  return <Suspense fallback={<Loading />}><Documentation /></Suspense>;
}

function Documentation() {
  const params = useSearchParams();
  const router = useRouter();
  const invs = useApi<Investigation[]>("/investigations");
  const providers = useApi<Page<Provider>>("/providers?limit=200");
  const template = useApi<TemplateSection[]>("/investigations/template");
  const selectedId = params.get("investigation");
  const newFor = params.get("provider");

  if (invs.error) return <ErrorState message={invs.error} onRetry={invs.reload} />;
  if (!invs.data || !providers.data || !template.data) return <Loading />;
  const current = invs.data.find((i) => String(i.id) === selectedId) ?? (newFor ? undefined : invs.data[0]);
  const without = providers.data.items.filter((p) => !invs.data!.some((i) => i.provider_id === p.id));

  async function start(providerId: string) {
    try {
      const inv = await api<Investigation>("/investigations", { method: "POST", json: { provider_id: Number(providerId) } });
      invs.reload();
      router.push(`/documentation?investigation=${inv.id}`);
    } catch (e) { toast.error((e as Error).message); }
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Provider onboarding documentation"
        description="A structured 15-section investigation template per provider, written for product and engineering. Export as Markdown or CSV."
        actions={<a href={`${API_URL}/investigations/export.csv`}><Button variant="outline"><Download />Export all (CSV)</Button></a>} />
      <div className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="space-y-3">
          <div className="rounded-xl border bg-card p-2">
            {invs.data.map((i) => (
              <button key={i.id} onClick={() => router.push(`/documentation?investigation=${i.id}`)}
                className={cn("w-full rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-muted", current?.id === i.id && "bg-muted")}>
                <div className="flex items-center gap-2 font-medium"><FileText className="size-4 text-muted-foreground" /><span className="truncate">{i.provider_name}</span></div>
                <div className="mt-1.5 flex items-center gap-2"><Progress value={i.completion} className="h-1.5" /><span className="text-xs tabular-nums text-muted-foreground">{i.completion}%</span></div>
              </button>
            ))}
          </div>
          {without.length > 0 && (
            <div className="rounded-xl border bg-card p-3">
              <Field label="Start an investigation">
                <NativeSelect defaultValue={newFor ?? ""} onChange={(e) => e.target.value && start(e.target.value)}>
                  <option value="">Select provider…</option>{without.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</NativeSelect>
              </Field>
            </div>
          )}
        </aside>
        {current ? <Editor key={`${current.id}-${current.updated_at}`} inv={current} template={template.data} provider={providers.data.items.find((p) => p.id === current.provider_id)} onSaved={invs.reload} />
          : <Empty>Select or start an investigation.</Empty>}
      </div>
    </div>
  );
}

function Editor({ inv, template, provider, onSaved }: { inv: Investigation; template: TemplateSection[]; provider?: Provider; onSaved: () => void }) {
  const fields = useMemo(() => ["author", "findings", ...template.map((t) => t.key)], [template]);
  const initial = useMemo(() => Object.fromEntries(fields.map((k) => [k, (inv[k] as string | null) ?? ""])), [fields, inv]);
  const [f, setF] = useState<Record<string, string>>(initial);
  const [busy, setBusy] = useState(false);
  const dirty = fields.some((k) => f[k] !== initial[k]);

  async function save() {
    setBusy(true);
    try {
      await api(`/investigations/${inv.id}`, { method: "PUT", json: f });
      toast.success("Investigation saved");
      onSaved();
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card px-4 py-3">
        <div>
          <div className="flex items-center gap-2 font-semibold">{inv.provider_name}{provider && <ProviderStatusBadge status={provider.status} />}</div>
          <div className="text-xs text-muted-foreground">Last updated {fmtDate(inv.updated_at)} · {inv.completion}% of template documented</div>
        </div>
        <div className="flex gap-2">
          <a href={`${API_URL}/investigations/${inv.id}/export?format=md`}><Button variant="outline" size="sm"><Download />Markdown</Button></a>
          <a href={`${API_URL}/investigations/${inv.id}/export?format=csv`}><Button variant="outline" size="sm"><Download />CSV</Button></a>
          <Button size="sm" onClick={save} disabled={!dirty || busy}><Save />{busy ? "Saving…" : dirty ? "Save changes" : "Saved"}</Button>
        </div>
      </div>
      <Section title="Summary">
        <div className="grid gap-3 md:grid-cols-[220px_1fr]">
          <Field label="Author"><Input value={f.author} onChange={(e) => setF({ ...f, author: e.target.value })} /></Field>
          <Field label="Summary of findings"><Textarea rows={3} value={f.findings} onChange={(e) => setF({ ...f, findings: e.target.value })} /></Field>
        </div>
      </Section>
      {template.map((t) => (
        <section key={t.key} className="rounded-xl border bg-card p-4">
          <label className="block">
            <span className="mb-1.5 flex items-center gap-2 text-sm font-semibold">
              <span className="grid size-5 place-items-center rounded bg-muted text-[11px] tabular-nums">{t.number}</span>{t.title}
              {!f[t.key]?.trim() && <span className="text-xs font-normal text-amber-700 dark:text-amber-400">not documented</span>}
            </span>
            <Textarea rows={t.key.startsWith("sample") ? 4 : 3} className={t.key.startsWith("sample") ? "font-mono text-xs" : ""}
              value={f[t.key]} onChange={(e) => setF({ ...f, [t.key]: e.target.value })} />
          </label>
        </section>
      ))}
    </div>
  );
}
