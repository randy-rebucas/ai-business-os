"use client";

import { useEffect } from "react";
import useSWR from "swr";

import { ApiError } from "@/lib/api";
import { MOOD_FONTS, type MoodKey } from "@/lib/fonts";
import { useOrgData } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Branding } from "@/lib/types";

const VARS = ["--brand-accent-light", "--brand-on-light", "--brand-accent-soft-light", "--brand-accent-dark",
  "--brand-on-dark", "--brand-accent-soft-dark", "--brand-fill-light", "--brand-on-fill-light", "--brand-fill-dark",
  "--brand-on-fill-dark", "--brand-note-light", "--brand-note-dark", "--brand-marker", "--mood-display",
  "--mood-text"] as const;

export function useBranding() {
  return useOrgData<Branding>("/api/v1/org/branding");
}

/** Applies the active workspace's accent and type mood to the document (tokens in globals.css). Only --brand-* and
 *  --mood-* are touched: status colours and the shell stay the platform's. Cleared when the workspace changes. */
export function BrandingApplier() {
  const { data } = useBranding();
  useEffect(() => {
    const root = document.documentElement.style;
    if (!data) return;
    const a = data.accent;
    const fonts = MOOD_FONTS[data.mood.key as MoodKey] ?? MOOD_FONTS.report;
    const values: Record<(typeof VARS)[number], string> = {
      "--brand-accent-light": a.light, "--brand-on-light": a.on_light, "--brand-accent-soft-light": a.soft_light,
      "--brand-accent-dark": a.dark, "--brand-on-dark": a.on_dark, "--brand-accent-soft-dark": a.soft_dark,
      "--brand-fill-light": a.fill_light, "--brand-on-fill-light": a.on_fill_light, "--brand-fill-dark": a.fill_dark,
      "--brand-on-fill-dark": a.on_fill_dark, "--brand-note-light": a.note_light, "--brand-note-dark": a.note_dark,
      "--brand-marker": a.marker, "--mood-display": fonts.display, "--mood-text": fonts.text,
    };
    for (const k of VARS) root.setProperty(k, values[k]);
    return () => {
      for (const k of VARS) root.removeProperty(k);
    };
  }, [data]);
  return null;
}

async function blobUrl([path, orgId]: [string, string]): Promise<string> {
  const res = await fetch(path, { headers: { "X-Org-Id": orgId, "X-Requested-With": "abos" }, credentials: "same-origin" });
  if (!res.ok) throw new ApiError(res.status, "logo_failed", "Could not load the logo");
  return URL.createObjectURL(await res.blob());
}

/** Object URL of the workspace logo (the endpoint needs the tenant header, so a plain <img src> can't fetch it). */
export function useLogoSrc(logoUrl: string | null | undefined) {
  const { orgId } = useSession();
  return useSWR(logoUrl && orgId ? [logoUrl, orgId] : null, blobUrl, { revalidateOnFocus: false }).data;
}
