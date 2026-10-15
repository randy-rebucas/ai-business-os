"use client";

import { useState } from "react";
import useSWR, { type SWRConfiguration } from "swr";

import { errorMessage } from "@/lib/forms";
import { useSession } from "@/lib/session";

/** Tenant-scoped GET. The cache key includes the active org so switching workspaces never shows stale data. */
export function useOrgData<T>(path: string | null, config?: SWRConfiguration<T>) {
  const { orgId } = useSession();
  return useSWR<T>(path && orgId ? [path, orgId] : null, config);
}

/** Poll every `ms` while `busy(data)` is true (e.g. documents still processing), otherwise not at all. */
export function pollWhile<T>(busy: (data: T) => boolean, ms = 2000): SWRConfiguration<T> {
  return { refreshInterval: (data?: T) => (data !== undefined && busy(data) ? ms : 0) };
}

/** Non-tenant GET for authenticated reference data. */
export function useGlobalData<T>(path: string | null) {
  return useSWR<T>(path ? [path, null] : null);
}

/** Small async-action helper: busy flag + error/success message. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>, success?: string) => {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      await fn();
      if (success) setDone(success);
      return true;
    } catch (err) {
      setError(errorMessage(err));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, done, run };
}
