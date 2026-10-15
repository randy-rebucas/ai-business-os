"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";

import { api, ApiError, setActiveOrgId } from "@/lib/api";
import type { Me, Membership } from "@/lib/types";

const ORG_KEY = "abos.activeOrg";

type SessionValue = {
  me: Me;
  membership: Membership | null;
  orgId: string | null;
  can: (permission: string) => boolean;
  switchOrg: (orgId: string) => void;
  refresh: () => Promise<unknown>;
  logout: () => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

function readStoredOrg(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(ORG_KEY);
  } catch {
    return null;
  }
}

function storeOrg(id: string) {
  try {
    localStorage.setItem(ORG_KEY, id);
  } catch {
    /* storage unavailable (private mode) — selection just won't persist */
  }
}

/** Wraps authenticated pages. Redirects to /login when there is no valid session. */
export function SessionProvider({ children, fallback }: { children: React.ReactNode; fallback: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { mutate: globalMutate } = useSWRConfig();
  const { data: me, error, mutate } = useSWR<Me>("/api/v1/auth/me", (p: string) => api<Me>(p), {
    shouldRetryOnError: false,
  });
  const [chosenOrg, setChosenOrg] = useState<string | null>(readStoredOrg);

  useEffect(() => {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [error, pathname, router]);

  // Active org: the chosen one if still a member, else the first membership.
  const orgId = useMemo(() => {
    if (!me) return null;
    const valid = me.memberships.find((m) => m.organization.id === chosenOrg);
    return valid?.organization.id ?? me.memberships[0]?.organization.id ?? null;
  }, [me, chosenOrg]);

  // Mutations read the active org from the api module; SWR reads pass it via the cache key.
  useEffect(() => setActiveOrgId(orgId), [orgId]);

  const switchOrg = useCallback(
    (id: string) => {
      storeOrg(id);
      setActiveOrgId(id);
      setChosenOrg(id);
      router.push("/app");
    },
    [router],
  );

  const logout = useCallback(async () => {
    try {
      await api("/api/v1/auth/logout", { method: "POST" });
    } finally {
      setActiveOrgId(null);
      await globalMutate(() => true, undefined, { revalidate: false });
      router.replace("/login");
    }
  }, [globalMutate, router]);

  const value = useMemo<SessionValue | null>(() => {
    if (!me) return null;
    const membership = me.memberships.find((m) => m.organization.id === orgId) ?? null;
    return {
      me,
      membership,
      orgId: membership ? orgId : null,
      can: (p) => !!membership?.permissions.includes(p),
      switchOrg,
      refresh: () => mutate(),
      logout,
    };
  }, [me, orgId, switchOrg, mutate, logout]);

  if (error && !(error instanceof ApiError && error.status === 401)) {
    return (
      <div role="alert" className="p-8 text-danger">
        Could not load your session: {error.message}
      </div>
    );
  }
  if (!value) return <>{fallback}</>;
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}
