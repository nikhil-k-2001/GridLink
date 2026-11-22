export function fmtDate(iso: string | null | undefined, withTime = true): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: withTime ? undefined : "numeric",
    hour: withTime ? "2-digit" : undefined, minute: withTime ? "2-digit" : undefined, timeZone: "UTC" }) + (withTime ? " UTC" : "");
}

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  const fut = diff < 0;
  const s = Math.abs(diff);
  const v = s < 60 ? `${Math.round(s)}s` : s < 3600 ? `${Math.round(s / 60)}m` : s < 86400 ? `${Math.round(s / 3600)}h` : `${Math.round(s / 86400)}d`;
  return fut ? `in ${v}` : `${v} ago`;
}

export function fmtNum(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-GB", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function minutesLabel(m: number | null | undefined): string {
  if (m === null || m === undefined) return "—";
  const a = Math.abs(m);
  const s = a < 60 ? `${Math.round(a)} min` : a < 1440 ? `${(a / 60).toFixed(1)} h` : `${(a / 1440).toFixed(1)} d`;
  return m < 0 ? `${s} ahead` : s;
}

export const humanise = (s: string | null | undefined) => (s ?? "").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const SOURCE_COLORS: Record<string, string> = {
  solar: "#e8a317", wind_onshore: "#3b82c4", wind_offshore: "#1e4f8a", biomass: "#5a8f3c", hydro: "#22a3b5",
  hydro_run_of_river: "#22a3b5", hydro_reservoir: "#167a87", other_renewable: "#9bbf4a", pumped_storage: "#6b5fb5",
  lignite: "#7a5236", hard_coal: "#4a4a4a", fossil_gas: "#d0703a", oil: "#8c2f39", nuclear: "#c9b200",
  other_conventional: "#9a9a9a", waste: "#a07a5a", geothermal: "#b5564a", total: "#334155", all: "#334155",
};
export const SOURCE_ORDER = ["nuclear", "lignite", "hard_coal", "fossil_gas", "oil", "other_conventional", "waste", "biomass",
  "hydro", "hydro_run_of_river", "hydro_reservoir", "pumped_storage", "geothermal", "other_renewable", "wind_offshore",
  "wind_onshore", "solar"];
