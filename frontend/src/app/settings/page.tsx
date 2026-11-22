"use client";
import { CheckCircle2, CircleDashed, ExternalLink } from "lucide-react";
import { API_URL } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { ErrorState, KV, Loading, PageHeader, Section } from "@/components/gridlink/page";
import { OriginBadge } from "@/components/gridlink/status";

interface Status { entsoe_token_configured: boolean; entsoe_base_url: string; gemini_configured: boolean; gemini_model: string;
  scheduler_enabled: boolean; http: { timeout_seconds: number; max_retries: number; backoff_base_seconds: number }; note: string }
interface CType { connector_type: string; provider: string; data_origin: string; description: string }

function Flag({ on, onText, offText }: { on: boolean; onText: string; offText: string }) {
  return on ? <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400"><CheckCircle2 className="size-4" />{onText}</span>
    : <span className="inline-flex items-center gap-1 text-muted-foreground"><CircleDashed className="size-4" />{offText}</span>;
}

export default function SettingsPage() {
  const { data, error, reload } = useApi<Status>("/settings/status");
  const types = useApi<CType[]>("/connectors/types");
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <Loading />;
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description={data.note} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="ENTSO-E Transparency Platform" description="Optional live integration using your own security token.">
          <KV items={[["Security token", <Flag key="t" on={data.entsoe_token_configured} onText="Configured" offText="Not configured" />],
            ["API base URL", <code key="u" className="text-xs">{data.entsoe_base_url}</code>]]} />
          <ol className="mt-4 list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
            <li>Create an account on <a className="text-primary hover:underline" href="https://transparency.entsoe.eu/" target="_blank" rel="noreferrer">transparency.entsoe.eu</a>.</li>
            <li>Request RESTful API access (see the platform help centre), then generate a token in your account settings.</li>
            <li>Add <code>ENTSOE_API_TOKEN=…</code> to <code>backend/.env</code> and restart the API.</li>
            <li>Sync the “ENTSO-E DE-LU – live API” connector. Until then, the simulated fixture connector is clearly labelled <OriginBadge origin="simulated" />.</li>
          </ol>
        </Section>
        <Section title="AI assistance (optional)" description="Gemini Developer API free tier. The integration pipeline never depends on it.">
          <KV items={[["Gemini API key", <Flag key="g" on={data.gemini_configured} onText="Configured" offText="Disabled" />], ["Model", data.gemini_model]]} />
          <p className="mt-4 text-sm text-muted-foreground">Set <code>GEMINI_API_KEY</code> in <code>backend/.env</code> to enable error summaries and dataset explanations. Only connector metadata and error text are sent — never credentials.</p>
        </Section>
        <Section title="Sync & reliability">
          <KV items={[["Background scheduler", <Flag key="s" on={data.scheduler_enabled} onText="Enabled (APScheduler)" offText="Manual sync only" />],
            ["HTTP timeout", `${data.http.timeout_seconds} s`], ["Max retries", String(data.http.max_retries)],
            ["Backoff", `exponential, base ${data.http.backoff_base_seconds} s + jitter; honours Retry-After`]]} />
        </Section>
        <Section title="API" description="FastAPI backend with OpenAPI documentation.">
          <KV items={[["Base URL", <code key="b" className="text-xs">{API_URL}</code>],
            ["Interactive docs", <a key="d" href={`${API_URL}/docs`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">{API_URL}/docs<ExternalLink className="size-3" /></a>]]} />
        </Section>
      </div>
      <Section title="Registered connector types" description="Adding a provider = one connector class implementing the contract + one mapping file.">
        <ul className="divide-y text-sm">{types.data?.map((t) => (
          <li key={t.connector_type} className="flex flex-wrap items-center gap-3 py-2"><code className="w-36">{t.connector_type}</code>
            <span className="w-20 text-muted-foreground">{t.provider}</span><OriginBadge origin={t.data_origin} /><span className="text-muted-foreground">{t.description}</span></li>))}</ul>
      </Section>
    </div>
  );
}
