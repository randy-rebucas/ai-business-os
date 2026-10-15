import Link from "next/link";

import { cn } from "@/lib/utils";

/* The signature move of the Annual Report world: figures set at report scale, each carrying a numbered note key, and
   a Notes list where every note says how the figure was counted and links to the records it came from. Notes must
   describe real data and real links — never decoration. */

export type ReportNote = { key: number; text: React.ReactNode; href?: string; linkLabel?: string };

/** A row of figures under a heavy ink rule. */
export function Figures({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <dl className={cn("grid border-t-[3px] border-rule sm:grid-cols-[repeat(auto-fit,minmax(11rem,1fr))]", className)}>
      {children}
    </dl>
  );
}

/** A note key. Inside a figure it is a true superscript sized against the numeral (em-based). */
export function NoteKey({ n, className }: { n: number; className?: string }) {
  return (
    <a
      href={`#note-${n}`}
      className={cn("ml-[0.08em] align-super text-[0.3em] font-bold leading-none text-note no-underline hover:underline", className)}
      aria-label={`Note ${n}`}
    >
      {n}
    </a>
  );
}

export function Figure({
  label,
  value,
  unit,
  note,
  detail,
  tone,
  size = "lg",
  children,
}: {
  label: string;
  value: React.ReactNode;
  unit?: string; // a currency or unit, set small beside the figure
  note?: number;
  detail?: React.ReactNode;
  tone?: "danger" | "warning";
  size?: "lg" | "md";
  children?: React.ReactNode;
}) {
  return (
    <div className="border-b border-border py-4 pr-6 sm:[&:not(:last-child)]:border-r sm:[&:not(:first-child)]:pl-6">
      <dt className="text-sm font-semibold text-fg">{label}</dt>
      <dd className="mt-1.5">
        <span
          className={cn(
            "figure-value font-display font-extrabold leading-none tracking-[-0.025em]",
            size === "lg" ? "text-[52px] sm:text-[64px]" : "text-[36px] sm:text-[44px]",
            tone === "danger" ? "text-danger" : tone === "warning" ? "text-warning" : "text-fg",
          )}
        >
          {value}
          {unit && <span className="ml-[0.15em] font-sans text-[0.3em] font-semibold tracking-normal text-muted">{unit}</span>}
          {note !== undefined && <NoteKey n={note} />}
        </span>
        {detail && <p className="mt-2 text-xs text-muted">{detail}</p>}
        {children && <div className="mt-3">{children}</div>}
      </dd>
    </div>
  );
}

/** "Notes to the figures": how each was counted and where its evidence is. */
export function Notes({ notes, title = "Notes", className }: { notes: ReportNote[]; title?: string; className?: string }) {
  if (!notes.length) return null;
  return (
    <section aria-label={title} className={cn("border-t-2 border-rule pt-3", className)}>
      <h2 className="font-display text-[15px] font-bold tracking-tight">{title}</h2>
      <ol className="mt-2 divide-y divide-border">
        {notes.map((n) => (
          <li key={n.key} id={`note-${n.key}`} className="report-note grid scroll-mt-24 grid-cols-[1.5rem_1fr] gap-2 py-2.5 text-sm">
            <span className="font-bold text-note">{n.key}</span>
            <p className="text-muted">
              {n.text}
              {n.href && (
                <>
                  {" "}
                  <Link href={n.href} className="font-semibold text-accent underline">
                    {n.linkLabel ?? "Open the records"}
                  </Link>
                </>
              )}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** A section of the report: heading under an ink rule, content set flat on the page — not a boxed card. */
export function ReportSection({ title, description, id, action, children, className }: {
  title: string; description?: React.ReactNode; id?: string; action?: React.ReactNode; children: React.ReactNode;
  className?: string;
}) {
  return (
    <section id={id} aria-label={title} className={cn("scroll-mt-24 border-t-2 border-rule pt-3", className)}>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="font-display text-lg font-bold tracking-tight">{title}</h2>
          {description && <p className="text-xs text-muted">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
