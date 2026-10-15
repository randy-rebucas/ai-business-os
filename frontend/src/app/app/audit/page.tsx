"use client";

import { ScrollText } from "lucide-react";
import { useState } from "react";

import { EmptyState, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Select } from "@/components/ui/form";
import { useOrgData } from "@/lib/hooks";
import { auditActionLabel } from "@/lib/labels";
import type { AuditEvent } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const FILTERS: [string, string][] = [
  ["", "All activity"],
  ["org.", "Workspace & members"],
  ["company.", "Company profile"],
];

function describe(e: AuditEvent): string | null {
  const d = e.data as Record<string, unknown>;
  if (Array.isArray(d.fields)) return `Fields: ${(d.fields as string[]).map((f) => f.replaceAll("_", " ")).join(", ")}`;
  if (d.role && typeof d.role === "string") return `Role: ${d.role}`;
  if (d.role && typeof d.role === "object") {
    const r = d.role as { from: string; to: string };
    return `Role: ${r.from} → ${r.to}`;
  }
  if (typeof d.name === "string") return d.name;
  return null;
}

export default function AuditPage() {
  const [filter, setFilter] = useState("");
  const { data, error } = useOrgData<AuditEvent[]>(`/api/v1/audit?limit=200${filter ? `&action=${encodeURIComponent(filter)}` : ""}`);
  return (
    <>
      <PageHeader
        title="Audit log"
        description="Every change in this workspace, recorded at the moment it was committed. Entries cannot be edited or deleted."
        actions={
          <Select aria-label="Filter activity" value={filter} onChange={(e) => setFilter(e.target.value)} className="w-56">
            {FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        }
      />
      {error ? <ErrorState error={error} /> : !data ? <Spinner /> : data.length === 0 ? (
        <EmptyState icon={ScrollText} title="No matching activity" />
      ) : (
        <Table label="Audit events">
          <thead>
            <tr><th className={th}>When</th><th className={th}>Action</th><th className={th}>Actor</th><th className={th}>Details</th></tr>
          </thead>
          <tbody>
            {data.map((e) => (
              <tr key={e.id}>
                <td className={`${td} whitespace-nowrap text-muted`}><time dateTime={e.created_at}>{formatDateTime(e.created_at)}</time></td>
                <td className={td}>
                  <p className="font-medium">{auditActionLabel(e.action)}</p>
                  <p className="ident text-xs text-subtle">{e.action}</p>
                </td>
                <td className={td}>{e.actor_name ?? <span className="text-subtle">{e.actor_type}</span>}</td>
                <td className={`${td} text-muted`}>{describe(e) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}
