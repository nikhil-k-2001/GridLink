import { cn } from "@/lib/utils";
import type { EvidenceLevel, HealthStatus } from "@/lib/types";
import { humanise } from "@/lib/format";
import { AlertTriangle, CheckCircle2, CircleAlert, FlaskConical, XCircle } from "lucide-react";

const pill = "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap";

const HEALTH: Record<HealthStatus, { cls: string; Icon: typeof CheckCircle2 }> = {
  healthy: { cls: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300", Icon: CheckCircle2 },
  warning: { cls: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300", Icon: AlertTriangle },
  degraded: { cls: "border-orange-300 bg-orange-50 text-orange-800 dark:border-orange-900 dark:bg-orange-950 dark:text-orange-300", Icon: CircleAlert },
  failed: { cls: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300", Icon: XCircle },
};

export function HealthBadge({ status, className }: { status: HealthStatus | string; className?: string }) {
  const h = HEALTH[status as HealthStatus] ?? HEALTH.warning;
  return <span className={cn(pill, h.cls, className)}><h.Icon className="size-3" />{humanise(status)}</span>;
}

const NEUTRAL = "border-border bg-muted text-muted-foreground";
const PROVIDER: Record<string, string> = {
  connected: HEALTH.healthy.cls,
  access_granted: "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300",
  integration_in_progress: "border-indigo-200 bg-indigo-50 text-indigo-800 dark:border-indigo-900 dark:bg-indigo-950 dark:text-indigo-300",
  access_requested: HEALTH.warning.cls,
  under_investigation: "border-violet-200 bg-violet-50 text-violet-800 dark:border-violet-900 dark:bg-violet-950 dark:text-violet-300",
  discovered: NEUTRAL,
  blocked: HEALTH.failed.cls,
};
export function ProviderStatusBadge({ status }: { status: string }) {
  return <span className={cn(pill, PROVIDER[status] ?? NEUTRAL)}>{humanise(status)}</span>;
}

const EVIDENCE: Record<EvidenceLevel, { cls: string; label: string; hint: string }> = {
  verified: { cls: HEALTH.healthy.cls, label: "Verified", hint: "Tested by GridLink against the live provider" },
  researched: { cls: PROVIDER.access_granted, label: "Researched", hint: "Taken from provider documentation" },
  assumption: { cls: "border-dashed border-amber-300 bg-transparent text-amber-800 dark:text-amber-300", label: "Assumption", hint: "Not yet confirmed — verify before relying on it" },
};
export function EvidenceBadge({ level }: { level: EvidenceLevel }) {
  const e = EVIDENCE[level];
  return <span title={e.hint} className={cn(pill, e.cls)}>{e.label}</span>;
}

export function OriginBadge({ origin, className }: { origin: string; className?: string }) {
  if (origin !== "simulated") return <span className={cn(pill, NEUTRAL, className)}>Real data</span>;
  return (
    <span className={cn(pill, "border-fuchsia-300 bg-fuchsia-50 text-fuchsia-800 dark:border-fuchsia-900 dark:bg-fuchsia-950 dark:text-fuchsia-300", className)}>
      <FlaskConical className="size-3" />Simulated
    </span>
  );
}

const SYNC: Record<string, string> = { success: HEALTH.healthy.cls, partial: HEALTH.warning.cls, failed: HEALTH.failed.cls, running: PROVIDER.access_granted };
export function SyncStatusBadge({ status }: { status: string }) {
  return <span className={cn(pill, SYNC[status] ?? NEUTRAL)}>{humanise(status)}</span>;
}

const QUALITY: Record<string, string> = { pass: HEALTH.healthy.cls, warn: HEALTH.warning.cls, fail: HEALTH.failed.cls };
export function QualityBadge({ status }: { status: string }) {
  return <span className={cn(pill, QUALITY[status] ?? NEUTRAL)}>{status === "warn" ? "Warning" : humanise(status)}</span>;
}

const FRESH: Record<string, string> = { fresh: HEALTH.healthy.cls, delayed: HEALTH.warning.cls, stale: HEALTH.degraded.cls };
export function FreshnessBadge({ status }: { status: string }) {
  return <span className={cn(pill, FRESH[status] ?? NEUTRAL)}>{humanise(status)}</span>;
}

export function StatusDot({ status }: { status: HealthStatus | string }) {
  const c = { healthy: "bg-emerald-500", warning: "bg-amber-500", degraded: "bg-orange-500", failed: "bg-red-500" }[status] ?? "bg-muted-foreground";
  return <span className={cn("inline-block size-2 shrink-0 rounded-full", c)} />;
}
