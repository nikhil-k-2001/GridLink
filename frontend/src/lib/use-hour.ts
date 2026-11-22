"use client";
import { useSyncExternalStore } from "react";

const HOUR = 3_600_000;
const subscribe = (cb: () => void) => { const t = setInterval(cb, 60_000); return () => clearInterval(t); };

/** Current time rounded up to the next full hour (ms). Stable within an hour, so it is safe in request URLs.
 *  Returns null during server prerendering, where "now" must not be frozen into the page. */
export function useHour(): number | null {
  return useSyncExternalStore(subscribe, () => Math.ceil(Date.now() / HOUR) * HOUR, () => null);
}
