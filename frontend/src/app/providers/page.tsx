"use client";
import Link from "next/link";
import { useState } from "react";
import { Plus, Search } from "lucide-react";
import { toast } from "sonner";
import { api, qs } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { PROVIDER_STATUSES as STATUSES, type Page, type Provider, type ProviderDetail } from "@/lib/types";
import { fmtDate, humanise } from "@/lib/format";
import { Empty, ErrorState, Loading, PageHeader } from "@/components/gridlink/page";
import { ProviderStatusBadge } from "@/components/gridlink/status";
import { Field, NativeSelect } from "@/components/gridlink/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function ProvidersPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [country, setCountry] = useState("");
  const { data, error, loading, reload } = useApi<Page<Provider>>(`/providers${qs({ q, status, country, limit: 200 })}`);
  const [open, setOpen] = useState(false);

  return (
    <div className="space-y-5">
      <PageHeader title="Provider discovery"
        description="Directory of energy data providers under investigation or integration. Each profile separates verified facts, researched documentation and unverified assumptions."
        actions={<Button onClick={() => setOpen(true)}><Plus />Add provider</Button>} />

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute top-2 left-2 size-4 text-muted-foreground" />
          <Input placeholder="Search providers" value={q} onChange={(e) => setQ(e.target.value)} className="w-64 pl-8" />
        </div>
        <NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}
        </NativeSelect>
        <Input placeholder="Country (e.g. DE)" value={country} maxLength={2} onChange={(e) => setCountry(e.target.value.toUpperCase())} className="w-36" />
        {data && <span className="text-xs text-muted-foreground">{data.total} providers</span>}
      </div>

      {error ? <ErrorState message={error} onRetry={reload} /> : loading && !data ? <Loading /> : !data?.items.length ? <Empty>No providers match.</Empty> : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <Table>
            <TableHeader><TableRow>
              <TableHead className="pl-4">Provider</TableHead><TableHead>Country</TableHead><TableHead>Status</TableHead>
              <TableHead>Authentication</TableHead><TableHead>Formats</TableHead><TableHead>Owner</TableHead>
              <TableHead>Investigated</TableHead><TableHead className="pr-4">Next action</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data.items.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="pl-4"><Link href={`/providers/${p.id}`} className="font-medium hover:underline">{p.name}</Link>
                    <div className="text-xs text-muted-foreground">{p.dataset_count} datasets · {p.connector_count} connectors</div></TableCell>
                  <TableCell className="font-mono text-xs">{p.country_code}</TableCell>
                  <TableCell><ProviderStatusBadge status={p.status} /></TableCell>
                  <TableCell className="max-w-48 truncate text-xs" title={p.authentication_type ?? ""}>{p.authentication_type ?? "—"}</TableCell>
                  <TableCell className="text-xs">{(p.data_formats ?? []).join(", ") || "—"}</TableCell>
                  <TableCell className="text-xs">{p.owner ?? "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{fmtDate(p.last_investigated_at, false)}</TableCell>
                  <TableCell className="max-w-72 pr-4 text-xs whitespace-normal text-muted-foreground"><span className="line-clamp-2" title={p.next_action ?? ""}>{p.next_action ?? "—"}</span></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <AddProviderDialog open={open} onOpenChange={setOpen} onCreated={reload} />
    </div>
  );
}

function AddProviderDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: () => void }) {
  const empty = { name: "", country_code: "", website: "", documentation_url: "", authentication_type: "", data_formats: "",
    description: "", status: "discovered", owner: "", next_action: "" };
  const [f, setF] = useState(empty);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof empty) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const body = { ...f, country_code: f.country_code.toUpperCase(),
        data_formats: f.data_formats.split(",").map((s) => s.trim()).filter(Boolean),
        website: f.website || null, documentation_url: f.documentation_url || null };
      const p = await api<ProviderDetail>("/providers", { method: "POST", json: body });
      toast.success(`${p.name} added to the directory`);
      setF(empty);
      onOpenChange(false);
      onCreated();
    } catch (err) {
      toast.error((err as Error).message);
    } finally { setBusy(false); }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Add provider</DialogTitle>
          <DialogDescription>Record a newly discovered data provider. Facts can be added with evidence levels on the provider page.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Name *" className="sm:col-span-2"><Input required minLength={2} value={f.name} onChange={set("name")} /></Field>
          <Field label="Country code *" hint="ISO 3166-1 alpha-2, or EU"><Input required pattern="[A-Za-z]{2}" value={f.country_code} onChange={set("country_code")} maxLength={2} /></Field>
          <Field label="Status"><NativeSelect value={f.status} onChange={set("status")}>{STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}</NativeSelect></Field>
          <Field label="Website"><Input type="url" placeholder="https://" value={f.website} onChange={set("website")} /></Field>
          <Field label="API documentation"><Input type="url" placeholder="https://" value={f.documentation_url} onChange={set("documentation_url")} /></Field>
          <Field label="Authentication"><Input placeholder="e.g. API key" value={f.authentication_type} onChange={set("authentication_type")} /></Field>
          <Field label="Data formats" hint="Comma separated"><Input placeholder="JSON, CSV" value={f.data_formats} onChange={set("data_formats")} /></Field>
          <Field label="Owner"><Input value={f.owner} onChange={set("owner")} /></Field>
          <Field label="Next action"><Input value={f.next_action} onChange={set("next_action")} /></Field>
          <Field label="Description" className="sm:col-span-2"><Textarea rows={3} value={f.description} onChange={set("description")} /></Field>
          <DialogFooter className="sm:col-span-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Add provider"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
