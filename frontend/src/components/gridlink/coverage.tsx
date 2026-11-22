import { cn } from "@/lib/utils";

export const COVERAGE: Record<string, { label: string; cls: string; group: "covered" | "progress" | "gap" }> = {
  covered: { label: "Covered", group: "covered", cls: "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300" },
  awaiting_authorisation: { label: "Awaiting owner", group: "progress", cls: "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300" },
  authorisation_not_requested: { label: "Ask owner", group: "progress", cls: "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300" },
  no_connector: { label: "No connector", group: "progress", cls: "border-indigo-200 bg-indigo-50 text-indigo-800 dark:border-indigo-900 dark:bg-indigo-950 dark:text-indigo-300" },
  route_blocked: { label: "Blocked", group: "gap", cls: "border-orange-300 bg-orange-50 text-orange-800 dark:border-orange-900 dark:bg-orange-950 dark:text-orange-300" },
  access_denied: { label: "Access denied", group: "gap", cls: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300" },
  authorisation_refused: { label: "Refused", group: "gap", cls: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300" },
  stale: { label: "Stale", group: "gap", cls: "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300" },
  simulated_only: { label: "Simulated only", group: "gap", cls: "border-fuchsia-300 bg-fuchsia-50 text-fuchsia-800 dark:border-fuchsia-900 dark:bg-fuchsia-950 dark:text-fuchsia-300" },
  no_route: { label: "No route", group: "gap", cls: "border-dashed border-red-300 bg-transparent text-red-700 dark:text-red-300" },
};

export function CoverageChip({ status, title, className }: { status: string; title?: string; className?: string }) {
  const c = COVERAGE[status] ?? { label: status, cls: "border-border bg-muted text-muted-foreground" };
  return <span title={title} className={cn("inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap", c.cls, className)}>{c.label}</span>;
}

/** Horizontal bar: covered / in progress / gap. */
export function CoverageBar({ covered, inProgress, gaps, className }: { covered: number; inProgress: number; gaps: number; className?: string }) {
  const total = Math.max(1, covered + inProgress + gaps);
  return (
    <div className={cn("flex h-2 w-full overflow-hidden rounded-full bg-muted", className)} role="img"
      aria-label={`${covered} covered, ${inProgress} in progress, ${gaps} gaps`}>
      <div className="bg-emerald-500" style={{ width: `${(100 * covered) / total}%` }} />
      <div className="bg-sky-400" style={{ width: `${(100 * inProgress) / total}%` }} />
      <div className="bg-orange-400" style={{ width: `${(100 * gaps) / total}%` }} />
    </div>
  );
}

export const FICTIONAL_NOTE = "Customers, plants and plant-level data are fictional / simulated to demonstrate the workflow.";

const SEV: Record<string, string> = {
  high: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300",
  medium: "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300",
  low: "border-border bg-muted text-muted-foreground",
};
export function SeverityBadge({ severity }: { severity: string }) {
  return <span className={cn("inline-flex rounded-md border px-1.5 py-0.5 text-xs font-medium capitalize", SEV[severity] ?? SEV.low)}>{severity}</span>;
}

const GENERIC: Record<string, string> = {
  done: COVERAGE.covered.cls, granted: COVERAGE.covered.cls, in_use: COVERAGE.covered.cls, resolved: COVERAGE.covered.cls,
  connected: COVERAGE.covered.cls, available: COVERAGE.covered.cls, partially_connected: COVERAGE.awaiting_authorisation.cls,
  in_progress: COVERAGE.awaiting_authorisation.cls, testing: COVERAGE.awaiting_authorisation.cls, in_review: COVERAGE.awaiting_authorisation.cls,
  sent: COVERAGE.awaiting_authorisation.cls, awaiting_reply: COVERAGE.awaiting_authorisation.cls, investigating: COVERAGE.no_connector.cls,
  access_in_progress: COVERAGE.no_connector.cls, mapping: COVERAGE.no_connector.cls, waiting_on_provider: COVERAGE.stale.cls,
  open: COVERAGE.route_blocked.cls, blocked: COVERAGE.route_blocked.cls, stalled: COVERAGE.route_blocked.cls, rejected: COVERAGE.access_denied.cls,
};
export function StatusPill({ status, className }: { status: string; className?: string }) {
  return <span className={cn("inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap",
    GENERIC[status] ?? "border-border bg-muted text-muted-foreground", className)}>{status.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())}</span>;
}
