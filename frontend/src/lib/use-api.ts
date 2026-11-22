"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

interface State<T> { key: string | null; data?: T; error?: string }

/** Fetch JSON from the GridLink API. State is only updated from the request callbacks, never synchronously. */
export function useApi<T>(path: string | null) {
  const [tick, setTick] = useState(0);
  const [state, setState] = useState<State<T>>({ key: null });
  const reload = useCallback(() => setTick((t) => t + 1), []);
  const key = path ? `${path}#${tick}` : null;

  useEffect(() => {
    if (!path || !key) return;
    let cancelled = false;
    api<T>(path)
      .then((d) => { if (!cancelled) setState({ key, data: d }); })
      .catch((e: Error) => { if (!cancelled) setState((s) => ({ key, data: s.data, error: e.message })); });
    return () => { cancelled = true; };
  }, [path, key]);

  return { data: state.data, error: state.error, loading: key !== null && state.key !== key, reload };
}
