"use client";
import { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SummarySeries } from "@/lib/types";
import { SOURCE_COLORS, SOURCE_ORDER, fmtNum, humanise } from "@/lib/format";

type Row = Record<string, number | string | null>;

export function pivot(series: SummarySeries[], keyOf: (s: SummarySeries) => string): Row[] {
  const map = new Map<string, Row>();
  for (const s of series) {
    const k = keyOf(s);
    for (const p of s.points) {
      const row = map.get(p.t) ?? { t: p.t };
      row[k] = p.v;
      map.set(p.t, row);
    }
  }
  return [...map.values()].sort((a, b) => String(a.t).localeCompare(String(b.t)));
}

const tick = (t: string, spanDays: number) => {
  const d = new Date(t);
  return spanDays > 2
    ? d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", timeZone: "UTC" }).replace(",", "") + "h"
    : d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
};

function spanDays(rows: Row[]) {
  if (rows.length < 2) return 0;
  return (new Date(String(rows[rows.length - 1].t)).getTime() - new Date(String(rows[0].t)).getTime()) / 86400_000;
}

const axisProps = { stroke: "var(--muted-foreground)", fontSize: 11, tickLine: false, axisLine: false } as const;

function ChartTooltip({ unit }: { unit: string }) {
  return (
    <Tooltip
      contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
      labelFormatter={(l) => new Date(String(l)).toLocaleString("en-GB", { timeZone: "UTC", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) + " UTC"}
      formatter={(v, name) => [v === null || v === undefined ? "no value" : `${fmtNum(Number(v))} ${unit}`, humanise(String(name).split("|")[0])]}
    />
  );
}

/** Stacked areas by energy source for one provider (definitions comparable within a provider). */
export function GenerationMixChart({ series, height = 340 }: { series: SummarySeries[]; height?: number }) {
  const sources = useMemo(() => {
    const present = new Set(series.map((s) => s.energy_source));
    return SOURCE_ORDER.filter((s) => present.has(s));
  }, [series]);
  const rows = useMemo(() => pivot(series, (s) => s.energy_source), [series]);
  const span = spanDays(rows);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={rows} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="t" tickFormatter={(t) => tick(t, span)} minTickGap={40} {...axisProps} />
        <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} width={40} {...axisProps} />
        <ChartTooltip unit="MW" />
        <Legend wrapperStyle={{ fontSize: 11 }} formatter={(v) => humanise(String(v))} iconType="square" iconSize={8} />
        {sources.map((s) => (
          <Area key={s} type="monotone" dataKey={s} stackId="1" stroke={SOURCE_COLORS[s] ?? "#888"} fill={SOURCE_COLORS[s] ?? "#888"}
            fillOpacity={0.85} strokeWidth={0} isAnimationActive={false} connectNulls={false} />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

const PALETTE = ["#2563eb", "#d97706", "#059669", "#db2777", "#7c3aed", "#0891b2", "#65a30d", "#dc2626"];

/** One line per series (e.g. same metric from different providers). Gaps stay gaps. */
export function ComparisonLineChart({ series, unit, height = 300 }: { series: SummarySeries[]; unit: string; height?: number }) {
  const key = (s: SummarySeries) => `${s.energy_source}|${s.provider_name}${s.data_origin === "simulated" ? " (simulated)" : ""}`;
  const rows = useMemo(() => pivot(series, key), [series]);
  const span = spanDays(rows);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rows} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="t" tickFormatter={(t) => tick(t, span)} minTickGap={40} {...axisProps} />
        <YAxis width={48} tickFormatter={(v) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v))} {...axisProps} />
        <ChartTooltip unit={unit} />
        <Legend wrapperStyle={{ fontSize: 11 }} formatter={(v) => { const [src, prov] = String(v).split("|"); return `${humanise(src)} — ${prov}`; }} iconSize={8} />
        {series.map((s, i) => (
          <Line key={key(s)} type="monotone" dataKey={key(s)} dot={false} isAnimationActive={false} connectNulls={false}
            stroke={series.length <= 3 ? PALETTE[i] : SOURCE_COLORS[s.energy_source] ?? PALETTE[i % PALETTE.length]}
            strokeWidth={1.6} strokeDasharray={s.data_origin === "simulated" ? "5 3" : undefined} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
