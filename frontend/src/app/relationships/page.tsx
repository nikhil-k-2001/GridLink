"use client";
import { useState } from "react";
import { ArrowDownLeft, ArrowUpRight, Clock, Plus } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { NEED_LABEL, type AccessRequest, type Contact, type FollowUp, type Interaction, type Page, type Provider } from "@/lib/types";
import { fmtDate, humanise, relTime } from "@/lib/format";
import { Empty, ErrorState, Loading, PageHeader, Section } from "@/components/gridlink/page";
import { StatusPill } from "@/components/gridlink/coverage";
import { Field, NativeSelect } from "@/components/gridlink/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

const REQ_STATUSES = ["draft", "sent", "awaiting_reply", "in_review", "granted", "rejected", "stalled"];

export default function RelationshipsPage() {
  const fus = useApi<FollowUp[]>("/follow-ups");
  const reqs = useApi<AccessRequest[]>("/access-requests");
  const ints = useApi<Interaction[]>("/interactions?limit=40");
  const contacts = useApi<Contact[]>("/contacts");
  const providers = useApi<Page<Provider>>("/providers?limit=200");
  const [logFor, setLogFor] = useState<AccessRequest | null>(null);
  const [newReq, setNewReq] = useState(false);
  const reloadAll = () => { fus.reload(); reqs.reload(); ints.reload(); };

  if (fus.error) return <ErrorState message={fus.error} onRetry={fus.reload} />;
  if (!fus.data || !reqs.data || !ints.data || !contacts.data || !providers.data) return <Loading />;

  async function setStatus(r: AccessRequest, status: string) {
    try { await api(`/access-requests/${r.id}`, { method: "PATCH", json: { status } }); toast.success("Request updated"); reloadAll(); }
    catch (e) { toast.error((e as Error).message); }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Provider relationships"
        description="Access is often won by persistence: who we asked, when, what they said, when to follow up — and which fallback to use when a channel stalls. Contacts are roles or shared channels, not named individuals."
        actions={<Button onClick={() => setNewReq(true)}><Plus />New access request</Button>} />

      <Section title="Follow-ups" description="Overdue first. A request without a scheduled next step is a request that will stall.">
        {fus.data.length ? <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{fus.data.map((f) => (
          <div key={f.request_id} className={cn("rounded-lg border p-3 text-sm", f.overdue && "border-red-300 bg-red-50/50 dark:border-red-900 dark:bg-red-950/20")}>
            <div className="flex items-start justify-between gap-2"><div className="font-medium">{f.provider}</div><StatusPill status={f.status} /></div>
            <div className="mt-0.5 text-xs text-muted-foreground">{f.subject}</div>
            <div className={cn("mt-2 flex items-center gap-1 text-xs", f.overdue ? "text-red-700 dark:text-red-400" : "text-muted-foreground")}><Clock className="size-3" />
              {f.next_follow_up ? `Follow-up ${relTime(f.next_follow_up)}` : f.due_date ? `Due ${relTime(f.due_date)}` : "No follow-up scheduled"}</div>
            <div className="text-xs text-muted-foreground">Last contact {f.days_since_contact ?? "—"} d ago · open {f.days_open} d</div>
            <Button size="xs" variant="outline" className="mt-2" onClick={() => setLogFor(reqs.data!.find((r) => r.id === f.request_id) ?? null)}>Log contact</Button>
          </div>))}</div> : <Empty>No open requests.</Empty>}
      </Section>

      <Section title="Access requests">
        <div className="-mx-4 -my-4 overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead className="pl-4">Provider</TableHead><TableHead>Request</TableHead><TableHead>Need</TableHead>
              <TableHead>Opened</TableHead><TableHead>Due</TableHead><TableHead>Contacts</TableHead><TableHead className="pr-4">Status</TableHead></TableRow></TableHeader>
            <TableBody>{reqs.data.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="pl-4 font-medium">{r.provider}<div className="font-mono text-xs text-muted-foreground">{r.country_code}</div></TableCell>
                <TableCell className="max-w-80 text-xs whitespace-normal">{r.subject}{r.fallback_route_id && <div className="text-[11px] text-amber-700 dark:text-amber-400">Fallback route mapped</div>}</TableCell>
                <TableCell className="text-xs">{NEED_LABEL[r.data_need] ?? r.data_need}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{fmtDate(r.opened_at, false)}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{r.closed_at ? `closed ${fmtDate(r.closed_at, false)}` : fmtDate(r.due_date, false)}</TableCell>
                <TableCell className="text-xs tabular-nums">{r.interactions}<Button size="xs" variant="ghost" className="ml-1" onClick={() => setLogFor(r)}>+ log</Button></TableCell>
                <TableCell className="pr-4"><NativeSelect value={r.status} aria-label="Request status" className="h-7 text-xs" onChange={(e) => setStatus(r, e.target.value)}>
                  {REQ_STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}</NativeSelect></TableCell>
              </TableRow>))}</TableBody>
          </Table>
        </div>
      </Section>

      <div className="grid gap-6 xl:grid-cols-3">
        <Section title="Recent interactions" className="xl:col-span-2">
          <ol className="space-y-3">{ints.data.map((i) => (
            <li key={i.id} className="flex gap-3 text-sm">
              <span className={cn("mt-0.5 grid size-6 shrink-0 place-items-center rounded-full", i.direction === "inbound" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" : "bg-muted text-muted-foreground")}>
                {i.direction === "inbound" ? <ArrowDownLeft className="size-3.5" /> : <ArrowUpRight className="size-3.5" />}</span>
              <div className="min-w-0"><div className="text-xs text-muted-foreground">{fmtDate(i.occurred_at)} · {i.channel} · <span className="font-medium text-foreground">{i.provider}</span>{i.contact ? ` · ${i.contact}` : ""}</div>
                <div>{i.summary}</div>
                {i.next_follow_up && <div className="text-xs text-muted-foreground">Next follow-up {fmtDate(i.next_follow_up, false)}</div>}</div>
            </li>))}</ol>
        </Section>
        <Section title="Contacts" description="Roles and channels per provider, incl. customer-side contacts who unlock access.">
          <ul className="divide-y text-sm">{contacts.data.map((c) => (
            <li key={c.id} className="py-2"><div className="font-medium">{c.role}</div>
              <div className="text-xs text-muted-foreground">{c.provider}{c.language ? ` · ${c.language}` : ""}</div>
              {c.notes && <div className="text-xs text-muted-foreground italic">{c.notes}</div>}</li>))}</ul>
        </Section>
      </div>

      {logFor && <LogDialog req={logFor} contacts={contacts.data.filter((c) => c.provider_id === logFor.provider_id)} onClose={() => setLogFor(null)} onSaved={reloadAll} />}
      <NewRequestDialog open={newReq} onOpenChange={setNewReq} providers={providers.data.items} onSaved={reloadAll} />
    </div>
  );
}

function LogDialog({ req, contacts, onClose, onSaved }: { req: AccessRequest; contacts: Contact[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ channel: "email", direction: "outbound", summary: "", contact_id: contacts[0]?.id ? String(contacts[0].id) : "", next_follow_up: "" });
  async function save() {
    try {
      await api("/interactions", { method: "POST", json: { provider_id: req.provider_id, access_request_id: req.id, channel: f.channel,
        direction: f.direction, summary: f.summary, contact_id: f.contact_id ? Number(f.contact_id) : null,
        next_follow_up: f.next_follow_up ? new Date(f.next_follow_up).toISOString() : null } });
      toast.success("Interaction logged"); onSaved(); onClose();
    } catch (e) { toast.error((e as Error).message); }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>Log contact — {req.provider}</DialogTitle><DialogDescription>{req.subject}</DialogDescription></DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Channel"><NativeSelect value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>
            {["email", "call", "meeting", "portal", "ticket", "linkedin"].map((c) => <option key={c}>{c}</option>)}</NativeSelect></Field>
          <Field label="Direction"><NativeSelect value={f.direction} onChange={(e) => setF({ ...f, direction: e.target.value })}>
            <option value="outbound">We contacted them</option><option value="inbound">They replied</option></NativeSelect></Field>
          <Field label="Contact" className="col-span-2"><NativeSelect value={f.contact_id} onChange={(e) => setF({ ...f, contact_id: e.target.value })}>
            <option value="">—</option>{contacts.map((c) => <option key={c.id} value={c.id}>{c.role}</option>)}</NativeSelect></Field>
          <Field label="Summary *" className="col-span-2"><Textarea rows={3} value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} /></Field>
          <Field label="Next follow-up" className="col-span-2"><Input type="date" value={f.next_follow_up} onChange={(e) => setF({ ...f, next_follow_up: e.target.value })} /></Field>
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={f.summary.length < 3} onClick={save}>Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NewRequestDialog({ open, onOpenChange, providers, onSaved }: { open: boolean; onOpenChange: (o: boolean) => void; providers: Provider[]; onSaved: () => void }) {
  const init = { provider_id: "", data_need: "production_metering", subject: "", due_date: "" };
  const [f, setF] = useState(init);
  async function save() {
    const p = providers.find((x) => String(x.id) === f.provider_id);
    if (!p) return;
    try {
      await api("/access-requests", { method: "POST", json: { provider_id: p.id, country_code: p.country_code, data_need: f.data_need,
        subject: f.subject, owner: "Data Integration TPM", due_date: f.due_date ? new Date(f.due_date).toISOString() : null } });
      toast.success("Access request created"); setF(init); onOpenChange(false); onSaved();
    } catch (e) { toast.error((e as Error).message); }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>New access request</DialogTitle><DialogDescription>Track a request to a data holder from first contact to granted.</DialogDescription></DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Provider *" className="col-span-2"><NativeSelect value={f.provider_id} onChange={(e) => setF({ ...f, provider_id: e.target.value })}>
            <option value="">Select…</option>{providers.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.country_code})</option>)}</NativeSelect></Field>
          <Field label="Data need"><NativeSelect value={f.data_need} onChange={(e) => setF({ ...f, data_need: e.target.value })}>
            {Object.entries(NEED_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</NativeSelect></Field>
          <Field label="Due date"><Input type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></Field>
          <Field label="Subject *" className="col-span-2"><Input value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} /></Field>
        </div>
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!f.provider_id || f.subject.length < 3} onClick={save}>Create</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
