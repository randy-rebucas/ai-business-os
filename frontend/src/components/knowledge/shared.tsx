import { Badge } from "@/components/ui/display";
import { ACCESS_LEVELS, DOC_STATUS } from "@/lib/labels";
import type { AccessLevel, DocStatus, DocumentRow } from "@/lib/types";

export const BUSY: DocStatus[] = ["uploaded", "queued", "processing"];
export const isBusy = (docs: DocumentRow[] | DocumentRow) =>
  (Array.isArray(docs) ? docs : [docs]).some((d) => BUSY.includes(d.status));

export function StatusBadge({ status }: { status: DocStatus }) {
  const s = DOC_STATUS[status];
  return (
    <Badge tone={s.tone}>
      {BUSY.includes(status) && (
        <span aria-hidden className="size-2.5 animate-spin rounded-full border-[1.5px] border-current border-t-transparent" />
      )}
      {s.label}
    </Badge>
  );
}

export function AccessBadge({ level }: { level: AccessLevel }) {
  if (level === "general") return null;
  return <Badge tone={level === "confidential" ? "danger" : "info"}>{ACCESS_LEVELS.find(([l]) => l === level)?.[1]}</Badge>;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
