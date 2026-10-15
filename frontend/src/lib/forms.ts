import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "@/lib/api";

// No JIT: zod would otherwise probe `new Function`, which the nonce CSP blocks. Every module that builds a schema
// imports this file, so the setting is in place before any schema is constructed.
z.config({ jitless: true });

/**
 * Map an API error onto a react-hook-form instance: field-level 422 errors go to their fields,
 * everything else is returned as a form-level message.
 */
export function applyApiError<T extends FieldValues>(err: unknown, setError: UseFormSetError<T>): string {
  if (err instanceof ApiError) {
    const fields = err.fieldErrors();
    const keys = Object.keys(fields);
    for (const k of keys) setError(k as Path<T>, { message: fields[k] });
    if (keys.length && err.code === "validation_error") return "Please correct the highlighted fields.";
    return err.message;
  }
  return "Unexpected error. Please try again.";
}

/** Message for errors outside react-hook-form (inline editors, buttons). */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const fields = Object.entries(err.fieldErrors());
    if (fields.length) return fields.map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`).join("; ");
    return err.message;
  }
  return "Unexpected error. Please try again.";
}

/** Empty strings from inputs become null so optional fields are cleared rather than stored blank. */
export function blankToNull<T extends Record<string, unknown>>(values: T): T {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(values)) out[k] = typeof v === "string" && v.trim() === "" ? null : v;
  return out as T;
}
