"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useState, type ReactNode } from "react";
import { AlertOctagon, BookOpen, Cable, FlaskConical, Gauge, Globe2, Handshake, LayoutDashboard, LineChart, ListOrdered, Menu, Settings, ShieldCheck, Sun, Waypoints, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Loading } from "@/components/gridlink/page";

const NAV = [
  { group: "This week", items: [{ href: "/", label: "Cockpit", Icon: LayoutDashboard }] },
  { group: "Demand", items: [
    { href: "/coverage", label: "Customers & plants", Icon: Sun },
    { href: "/prioritisation", label: "Prioritisation", Icon: ListOrdered }] },
  { group: "Access", items: [
    { href: "/countries", label: "Country access maps", Icon: Globe2 },
    { href: "/providers", label: "Providers", Icon: Waypoints },
    { href: "/relationships", label: "Relationships", Icon: Handshake },
    { href: "/api-bench", label: "API test bench", Icon: FlaskConical },
    { href: "/documentation", label: "Onboarding docs", Icon: BookOpen }] },
  { group: "Data", items: [
    { href: "/connectors", label: "Connectors", Icon: Cable },
    { href: "/quality", label: "Data quality", Icon: ShieldCheck },
    { href: "/issues", label: "Data issues", Icon: AlertOctagon },
    { href: "/explorer", label: "Energy explorer", Icon: LineChart }] },
  { group: "", items: [{ href: "/settings", label: "Settings", Icon: Settings }] },
];

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2 px-2">
      <span className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground"><Gauge className="size-4" /></span>
      <span className="leading-tight">
        <span className="block text-sm font-semibold tracking-tight">GridLink</span>
        <span className="block text-[11px] text-muted-foreground">Market connections workspace</span>
      </span>
    </Link>
  );
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  return (
    <nav className="flex flex-col gap-3">
      {NAV.map(({ group, items }) => (
        <div key={group || "misc"} className="flex flex-col gap-0.5">
          {group && <div className="px-2.5 pb-0.5 text-[10px] font-semibold tracking-wider text-muted-foreground/80 uppercase">{group}</div>}
          {items.map(({ href, label, Icon }) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link key={href} href={href} onClick={onNavigate}
                className={cn("flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors",
                  active ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground")}>
                <Icon className="size-4" />{label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-dvh bg-background">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col gap-5 overflow-y-auto border-r bg-sidebar px-3 py-4 lg:flex">
        <Brand />
        <Suspense fallback={<div className="h-64" />}><Nav /></Suspense>
        <div className="mt-auto rounded-lg border bg-background p-3 text-[11px] leading-relaxed text-muted-foreground">
          Real market data: Bundesnetzagentur | SMARD.de (CC BY 4.0).<br />
          Customers, plants &amp; DSO data are <span className="font-medium text-foreground">fictional / simulated</span>.
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b bg-background/90 px-4 backdrop-blur lg:hidden">
          <button aria-label="Open navigation" onClick={() => setOpen(true)} className="rounded-md p-1 hover:bg-muted"><Menu className="size-5" /></button>
          <Brand />
        </header>
        {open && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-black/30" onClick={() => setOpen(false)} />
            <div className="absolute inset-y-0 left-0 flex w-64 flex-col gap-5 overflow-y-auto bg-sidebar p-4 shadow-xl">
              <div className="flex items-center justify-between"><Brand /><button aria-label="Close" onClick={() => setOpen(false)}><X className="size-5" /></button></div>
              <Suspense fallback={null}><Nav onNavigate={() => setOpen(false)} /></Suspense>
            </div>
          </div>
        )}
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6"><Suspense fallback={<Loading />}>{children}</Suspense></main>
      </div>
    </div>
  );
}
