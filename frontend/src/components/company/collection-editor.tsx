"use client";

import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { Button } from "@/components/ui/button";
import { Alert, Badge } from "@/components/ui/display";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { CollectionItem } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

export type FieldDef = {
  name: string;
  label: string;
  kind: "text" | "textarea" | "select" | "number" | "date" | "checkbox" | "department";
  options?: [string, string][];
  required?: boolean;
  hint?: string;
  wide?: boolean;
};

export type CollectionDef = {
  key: string; // API segment: /api/v1/company/{key}
  noun: string; // "location"
  title: (item: CollectionItem) => string;
  summary?: (item: CollectionItem, depts: Map<string, string>) => (string | null | undefined)[];
  badge?: (item: CollectionItem) => string | null;
  fields: FieldDef[];
};

type Values = Record<string, string | boolean>;

function toValues(def: CollectionDef, item?: CollectionItem): Values {
  const out: Values = {};
  for (const f of def.fields) {
    const v = item?.[f.name];
    if (f.kind === "checkbox") out[f.name] = Boolean(v);
    else out[f.name] = v === null || v === undefined ? (f.kind === "select" && f.options ? f.options[0][0] : "") : String(v);
  }
  return out;
}

function toBody(def: CollectionDef, values: Values): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const f of def.fields) {
    const v = values[f.name];
    if (f.kind === "checkbox") body[f.name] = Boolean(v);
    else if (typeof v === "string" && v.trim() === "") body[f.name] = null;
    else if (f.kind === "number") body[f.name] = Number(v);
    else body[f.name] = typeof v === "string" ? v.trim() : v;
  }
  return body;
}

function ItemForm({
  def,
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  def: CollectionDef;
  initial: Values;
  submitLabel: string;
  onSubmit: (body: Record<string, unknown>) => Promise<void>;
  onCancel?: () => void;
}) {
  const [values, setValues] = useState<Values>(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: depts } = useOrgData<CollectionItem[]>(
    def.fields.some((f) => f.kind === "department") ? "/api/v1/company/departments" : null,
  );
  const set = (name: string, v: string | boolean) => setValues((cur) => ({ ...cur, [name]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const missing = def.fields.find((f) => f.required && !String(values[f.name] ?? "").trim());
    if (missing) {
      setError(`${missing.label} is required.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit(toBody(def, values));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-4 rounded-md border border-border bg-surface/60 p-4">
      {error && <Alert tone="danger">{error}</Alert>}
      <div className="grid gap-4 sm:grid-cols-2">
        {def.fields.map((f) => {
          if (f.kind === "checkbox") {
            return (
              <Checkbox
                key={f.name}
                label={f.label}
                hint={f.hint}
                className="sm:col-span-2"
                checked={Boolean(values[f.name])}
                onChange={(e) => set(f.name, e.target.checked)}
              />
            );
          }
          return (
            <Field
              key={f.name}
              label={f.required ? f.label : `${f.label} (optional)`}
              hint={f.hint}
              className={cn((f.wide || f.kind === "textarea") && "sm:col-span-2")}
            >
              {(p) =>
                f.kind === "textarea" ? (
                  <Textarea {...p} rows={3} value={String(values[f.name])} onChange={(e) => set(f.name, e.target.value)} />
                ) : f.kind === "select" ? (
                  <Select {...p} value={String(values[f.name])} onChange={(e) => set(f.name, e.target.value)}>
                    {f.options?.map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </Select>
                ) : f.kind === "department" ? (
                  <Select {...p} value={String(values[f.name])} onChange={(e) => set(f.name, e.target.value)}>
                    <option value="">No department</option>
                    {depts?.map((d) => (
                      <option key={d.id} value={d.id}>
                        {String(d.name)}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Input
                    {...p}
                    type={f.kind === "number" ? "number" : f.kind === "date" ? "date" : "text"}
                    inputMode={f.kind === "number" ? "decimal" : undefined}
                    value={String(values[f.name])}
                    onChange={(e) => set(f.name, e.target.value)}
                  />
                )
              }
            </Field>
          );
        })}
      </div>
      <div className="flex gap-2">
        <Button type="submit" size="sm" loading={busy}>
          {submitLabel}
        </Button>
        {onCancel && (
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

/** List + add + inline edit + delete for one company profile collection. Saves immediately. */
export function CollectionEditor({ def, readOnly }: { def: CollectionDef; readOnly?: boolean }) {
  const { orgId } = useSession();
  const { mutate } = useSWRConfig();
  const path = `/api/v1/company/${def.key}`;
  const { data: items, error, isLoading } = useOrgData<CollectionItem[]>(path);
  const { data: depts } = useOrgData<CollectionItem[]>(
    def.fields.some((f) => f.kind === "department") ? "/api/v1/company/departments" : null,
  );
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);
  const deptNames = new Map((depts ?? []).map((d) => [d.id, String(d.name)]));

  const refresh = async () => {
    await mutate([path, orgId]);
    await mutate(["/api/v1/company/completeness", orgId]);
    if (def.key === "departments") await mutate(["/api/v1/company/job-roles", orgId]);
  };

  const remove = async (item: CollectionItem) => {
    if (!window.confirm(`Delete ${def.noun} "${def.title(item)}"?`)) return;
    setRowError(null);
    try {
      await api(`${path}/${item.id}`, { method: "DELETE", org: true });
      await refresh();
    } catch (err) {
      setRowError(errorMessage(err));
    }
  };

  if (error) return <Alert tone="danger">{errorMessage(error)}</Alert>;
  if (isLoading || !items) return <p className="text-sm text-muted">Loading…</p>;

  return (
    <div className="space-y-3">
      {rowError && <Alert tone="danger">{rowError}</Alert>}
      {items.length === 0 && !adding && <p className="text-sm text-muted">Nothing added yet.</p>}
      <ul className="space-y-2">
        {items.map((item) =>
          editing === item.id ? (
            <li key={item.id}>
              <ItemForm
                def={def}
                initial={toValues(def, item)}
                submitLabel="Save changes"
                onCancel={() => setEditing(null)}
                onSubmit={async (body) => {
                  await api(`${path}/${item.id}`, { method: "PATCH", body, org: true });
                  setEditing(null);
                  await refresh();
                }}
              />
            </li>
          ) : (
            <li
              key={item.id}
              className="flex items-start justify-between gap-3 rounded-md border border-border bg-bg-2 px-4 py-3"
            >
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-fg">
                  {def.title(item)}
                  {def.badge?.(item) && <Badge tone="info">{def.badge(item)}</Badge>}
                </p>
                {def.summary && (
                  <p className="mt-0.5 text-xs text-muted">
                    {def.summary(item, deptNames).filter(Boolean).join(" · ") || "—"}
                  </p>
                )}
              </div>
              {!readOnly && (
                <div className="flex shrink-0 gap-1">
                  <Button variant="ghost" size="icon" aria-label={`Edit ${def.title(item)}`} onClick={() => setEditing(item.id)}>
                    <Pencil />
                  </Button>
                  <Button variant="ghost" size="icon" aria-label={`Delete ${def.title(item)}`} onClick={() => remove(item)}>
                    <Trash2 />
                  </Button>
                </div>
              )}
            </li>
          ),
        )}
      </ul>
      {!readOnly &&
        (adding ? (
          <ItemForm
            def={def}
            initial={toValues(def)}
            submitLabel={`Add ${def.noun}`}
            onCancel={() => setAdding(false)}
            onSubmit={async (body) => {
              await api(path, { method: "POST", body, org: true });
              setAdding(false);
              await refresh();
            }}
          />
        ) : (
          <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
            <Plus /> Add {def.noun}
          </Button>
        ))}
    </div>
  );
}

// ---- collection definitions (mirror abos/company/schemas.py) -------------------------------------------------

const opt = (...vals: string[]): [string, string][] =>
  vals.map((v) => [v, v.charAt(0).toUpperCase() + v.slice(1).replaceAll("_", " ")]);

export const COLLECTIONS: Record<string, CollectionDef> = {
  offerings: {
    key: "offerings",
    noun: "product or service",
    title: (i) => String(i.name),
    badge: (i) => (i.kind === "service" ? "Service" : "Product"),
    summary: (i) => [i.sku ? `SKU ${i.sku}` : null, i.pricing_note as string, i.description as string],
    fields: [
      { name: "name", label: "Name", kind: "text", required: true },
      { name: "kind", label: "Type", kind: "select", options: opt("product", "service") },
      { name: "sku", label: "SKU / code", kind: "text" },
      { name: "pricing_note", label: "Pricing note", kind: "text", hint: "As you'd describe it, e.g. \"from ₱1,200/month\"." },
      { name: "description", label: "Description", kind: "textarea" },
    ],
  },
  locations: {
    key: "locations",
    noun: "location",
    title: (i) => String(i.name),
    badge: (i) => (i.is_primary ? "Primary" : null),
    summary: (i) => [String(i.kind).replace("_", " "), [i.city, i.country].filter(Boolean).join(", "), i.timezone as string],
    fields: [
      { name: "name", label: "Name", kind: "text", required: true },
      { name: "kind", label: "Type", kind: "select", options: opt("headquarters", "branch", "office", "store", "warehouse", "factory", "remote", "other") },
      { name: "city", label: "City", kind: "text" },
      { name: "country", label: "Country", kind: "text" },
      { name: "timezone", label: "Time zone override", kind: "text", hint: "Only if different from the company, e.g. Asia/Singapore." },
      { name: "address", label: "Address", kind: "textarea" },
      { name: "is_primary", label: "Primary location", kind: "checkbox" },
    ],
  },
  departments: {
    key: "departments",
    noun: "department",
    title: (i) => String(i.name),
    summary: (i) => [i.head_name ? `Head: ${i.head_name}` : null, i.description as string],
    fields: [
      { name: "name", label: "Name", kind: "text", required: true },
      { name: "head_name", label: "Department head", kind: "text" },
      { name: "description", label: "What it does", kind: "textarea" },
    ],
  },
  "job-roles": {
    key: "job-roles",
    noun: "job role",
    title: (i) => String(i.title),
    summary: (i, d) => [i.department_id ? d.get(String(i.department_id)) : null, i.headcount != null ? `${i.headcount} people` : null],
    fields: [
      { name: "title", label: "Title", kind: "text", required: true },
      { name: "department_id", label: "Department", kind: "department" },
      { name: "headcount", label: "Headcount", kind: "number" },
      { name: "description", label: "Responsibilities", kind: "textarea" },
    ],
  },
  objectives: {
    key: "objectives",
    noun: "objective",
    title: (i) => String(i.title),
    badge: (i) => (i.status !== "active" ? String(i.status) : null),
    summary: (i, d) => [
      i.kpi_name ? `KPI: ${i.kpi_name}${i.kpi_target != null ? ` → ${Number(i.kpi_target).toLocaleString()} ${i.kpi_unit ?? ""}` : ""}` : null,
      i.target_date ? `by ${formatDate(String(i.target_date))}` : null,
      i.department_id ? d.get(String(i.department_id)) : null,
    ],
    fields: [
      { name: "title", label: "Objective", kind: "text", required: true, wide: true },
      { name: "kpi_name", label: "KPI", kind: "text", hint: "e.g. Monthly revenue, NPS, days sales outstanding." },
      { name: "kpi_target", label: "Target value", kind: "number" },
      { name: "kpi_unit", label: "Unit", kind: "text", hint: "e.g. PHP, %, days." },
      { name: "target_date", label: "Target date", kind: "date" },
      { name: "department_id", label: "Owning department", kind: "department" },
      { name: "status", label: "Status", kind: "select", options: opt("active", "achieved", "dropped") },
      { name: "description", label: "Details", kind: "textarea" },
    ],
  },
  processes: {
    key: "processes",
    noun: "process",
    title: (i) => String(i.name),
    summary: (i, d) => [i.department_id ? d.get(String(i.department_id)) : null, i.frequency as string,
      i.approval_procedure ? "Has approval procedure" : null],
    fields: [
      { name: "name", label: "Process", kind: "text", required: true },
      { name: "frequency", label: "How often", kind: "text", hint: "e.g. daily, per order, month-end." },
      { name: "department_id", label: "Owning department", kind: "department" },
      { name: "description", label: "How it works today", kind: "textarea" },
      { name: "approval_procedure", label: "Approval procedure", kind: "textarea", hint: "Who approves what, and above which amounts." },
    ],
  },
  software: {
    key: "software",
    noun: "software system",
    title: (i) => String(i.name),
    badge: (i) => (i.integration_wanted ? "Integration wanted" : null),
    summary: (i) => [String(i.category).replaceAll("_", " "), i.notes as string],
    fields: [
      { name: "name", label: "Name", kind: "text", required: true },
      { name: "category", label: "Category", kind: "select", options: opt("accounting", "crm", "erp", "inventory", "pos", "hr", "payroll", "marketing", "support", "project_management", "communication", "ecommerce", "spreadsheet", "other") },
      { name: "notes", label: "Notes", kind: "textarea" },
      { name: "integration_wanted", label: "We'd like AI employees to work with this system", kind: "checkbox" },
    ],
  },
  challenges: {
    key: "challenges",
    noun: "challenge",
    title: (i) => String(i.title),
    badge: (i) => `${String(i.severity)} impact`,
    summary: (i, d) => [i.department_id ? d.get(String(i.department_id)) : null, i.description as string],
    fields: [
      { name: "title", label: "Challenge", kind: "text", required: true, wide: true },
      { name: "severity", label: "Impact", kind: "select", options: [["medium", "Medium"], ["high", "High"], ["low", "Low"]] },
      { name: "department_id", label: "Department", kind: "department" },
      { name: "description", label: "Details", kind: "textarea" },
    ],
  },
};
