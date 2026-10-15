import { AlertTriangle, Ban, Check, CheckCircle2, CircleDashed, Info, Minus, XCircle } from "lucide-react";

import type { Tone } from "@/lib/labels";
import { cn } from "@/lib/utils";

const toneClass: Record<Tone, string> = {
  success: "border-success/35 bg-success/10 text-success",
  info: "border-info/35 bg-info/10 text-info",
  warning: "border-warning/35 bg-warning/10 text-warning",
  danger: "border-danger/35 bg-danger/10 text-danger",
  neutral: "border-border-strong bg-surface text-muted",
};

// State is shape + word, never hue alone: done is a check, pending is dashed, refused is struck.
const toneGlyph = { success: Check, info: Info, warning: CircleDashed, danger: Ban, neutral: Minus };

/** Status badge: a glyph and a label always accompany the colour. */
export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: React.ReactNode; className?: string }) {
  const Glyph = toneGlyph[tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-xs font-semibold whitespace-nowrap",
        toneClass[tone],
        className,
      )}
    >
      <Glyph aria-hidden className="size-3 shrink-0" strokeWidth={2.5} />
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
      className={cn("flex gap-3 rounded-sm border p-3 text-sm", toneClass[tone], className)}
    >
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <div className="space-y-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="text-fg/85">{children}</div>}
      </div>
    </div>
  );
}

/** A sheet of the report: white on the paper ground, hairline edge, no shadow. */
export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return <section className={cn("rounded-sm border border-border bg-bg-2", className)}>{children}</section>;
}

export function CardHeader({ title, description, action }: { title: string; description?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-3.5">
      <div className="min-w-0">
        <h2 className="font-display text-[15px] font-bold tracking-tight text-fg">{title}</h2>
        {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/** Page title under a heavy ink rule, like a report section. `context` (period, department, time zone) reads below it. */
export function PageHeader({
  title,
  description,
  actions,
  context,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  context?: React.ReactNode;
}) {
  return (
    <header className="mb-7 border-t-[3px] border-rule pt-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-display text-[28px] font-extrabold leading-tight tracking-[-0.015em] text-fg sm:text-[32px]">{title}</h1>
          {context && <div className="mt-1 text-sm font-medium text-subtle">{context}</div>}
          {description && <p className="mt-2 max-w-2xl text-sm text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
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
    <div className="rounded-sm border border-dashed border-border-strong bg-bg-2/60 px-6 py-10 text-center">
      <div className="mx-auto max-w-sm space-y-3">
        {Icon && <Icon className="mx-auto size-7 text-subtle" />}
        <p className="font-display font-bold text-fg">{title}</p>
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
    // No box of its own: the ink-ruled head carries the table, inside a sheet or flat on a report section.
    <div className="overflow-x-auto">
      <table aria-label={label} className="w-full text-left text-sm">
        {children}
      </table>
    </div>
  );
}

export const th = "border-b-2 border-rule px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted";
export const td = "border-b border-border px-4 py-3 align-top";

export function ProgressBar({ value, label }: { value: number; label: string }) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
      className="h-1.5 w-full overflow-hidden rounded-sm bg-surface-2"
    >
      <div className="h-full bg-accent transition-[width] duration-500 ease-out-expo" style={{ width: `${value}%` }} />
    </div>
  );
}

/** A quantity against a hard limit (budget, daily runs): the fill stops at the end mark, and going over is shown. */
export function Capacity({ used, limit, label, format = String }: {
  used: number; limit: number; label: string; format?: (n: number) => string;
}) {
  const pct = limit > 0 ? (used / limit) * 100 : used > 0 ? 100 : 0;
  const over = used >= limit && limit > 0;
  return (
    <div className="space-y-1">
      <div
        role="meter"
        aria-label={label}
        aria-valuenow={used}
        aria-valuemin={0}
        aria-valuemax={limit}
        aria-valuetext={`${format(used)} of ${format(limit)}`}
        className="relative h-2 bg-surface-2"
      >
        <div className={cn("h-full transition-[width] duration-500 ease-out-expo", over ? "bg-danger" : "bg-accent")}
          style={{ width: `${Math.min(pct, 100)}%` }} />
        <span aria-hidden className="absolute -top-1 right-0 h-4 w-0.5 bg-rule" />
      </div>
      <p className={cn("text-xs", over ? "font-semibold text-danger" : "text-muted")}>
        {format(used)} of {format(limit)}{over ? " — limit reached" : ` · ${Math.round(pct)}%`}
      </p>
    </div>
  );
}
