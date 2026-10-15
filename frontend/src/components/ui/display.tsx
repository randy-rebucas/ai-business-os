import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";

import type { Tone } from "@/lib/labels";
import { cn } from "@/lib/utils";

const toneClass: Record<Tone, string> = {
  success: "border-success/35 bg-success/10 text-success",
  info: "border-info/35 bg-info/10 text-info",
  warning: "border-warning/35 bg-warning/10 text-warning",
  danger: "border-danger/35 bg-danger/10 text-danger",
  neutral: "border-border-strong bg-surface text-muted",
};

const toneDot: Record<Tone, string> = {
  success: "bg-success",
  info: "bg-info",
  warning: "bg-warning",
  danger: "bg-danger",
  neutral: "bg-subtle",
};

/** Status badge: color is never the only signal — the label is always present. */
export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        toneClass[tone],
        className,
      )}
    >
      <span aria-hidden className={cn("size-1.5 rounded-full", toneDot[tone])} />
      {children}
    </span>
  );
}

const alertIcon = { success: CheckCircle2, info: Info, warning: AlertTriangle, danger: XCircle, neutral: Info };

export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: Tone;
  title?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  const Icon = alertIcon[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn("flex gap-3 rounded-md border p-3 text-sm", toneClass[tone], className)}
    >
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <div className="space-y-1">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className="text-fg/85">{children}</div>}
      </div>
    </div>
  );
}

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return <section className={cn("rounded-lg border border-border bg-bg-2 shadow-sm", className)}>{children}</section>;
}

export function CardHeader({ title, description, action }: { title: string; description?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-fg">{title}</h2>
        {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  eyebrow?: React.ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-medium uppercase tracking-wide text-subtle">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-fg">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 p-6 text-sm text-muted">
      <span aria-hidden className="size-4 animate-spin rounded-full border-2 border-muted border-t-transparent" />
      {label}…
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed border-border-strong px-6 py-10 text-center">
      <div className="mx-auto max-w-sm space-y-3">
        {Icon && <Icon className="mx-auto size-7 text-subtle" />}
        <p className="font-medium text-fg">{title}</p>
        {children && <div className="text-sm text-muted">{children}</div>}
        {action && <div className="pt-1">{action}</div>}
      </div>
    </div>
  );
}

export function ErrorState({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <Alert tone="danger" title="Something went wrong">
      <p>{error.message}</p>
      {retry && (
        <button type="button" onClick={retry} className="mt-2 text-sm underline underline-offset-2">
          Try again
        </button>
      )}
    </Alert>
  );
}

/** Definition list row for metadata panels. */
export function Meta({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-3 py-1.5 text-sm">
      <dt className="text-muted">{label}</dt>
      <dd className={cn("min-w-0 text-fg", mono && "ident")}>{children ?? "—"}</dd>
    </div>
  );
}

export function Table({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-bg-2">
      <table aria-label={label} className="w-full text-left text-sm">
        {children}
      </table>
    </div>
  );
}

export const th = "border-b border-border bg-surface px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-muted";
export const td = "border-b border-border/70 px-4 py-3 align-top";

export function ProgressBar({ value, label }: { value: number; label: string }) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
      className="h-2 w-full overflow-hidden rounded-full bg-surface-2"
    >
      <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${value}%` }} />
    </div>
  );
}
