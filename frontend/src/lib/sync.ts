"use client";
import { toast } from "sonner";
import { api } from "./api";
import { fmtNum } from "./format";
import type { SyncLog } from "./types";

export async function triggerSync(c: { id: number; connector_name: string }): Promise<SyncLog | undefined> {
  try {
    const log = await api<SyncLog>(`/connectors/${c.id}/sync`, { method: "POST", json: {} });
    const msg = `${c.connector_name}: ${log.status} — ${fmtNum(log.records_inserted)} new, ${fmtNum(log.records_updated)} updated, ${fmtNum(log.records_unchanged)} unchanged, ${fmtNum(log.records_failed)} rejected`;
    if (log.status === "failed") toast.error(`${c.connector_name}: sync failed — ${log.error_message ?? log.error_code}`);
    else if (log.status === "partial") toast.warning(msg);
    else toast.success(msg);
    return log;
  } catch (e) { toast.error((e as Error).message); }
}
