import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const dateOnly = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTime.format(new Date(iso)) : "—";
}

export function formatDate(iso: string | null | undefined): string {
  // Date-only values ("2026-12-25") are calendar dates: render them without a time-zone shift.
  if (!iso) return "—";
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? dateOnly.format(new Date(`${iso}T00:00:00`)) : dateOnly.format(new Date(iso));
}
