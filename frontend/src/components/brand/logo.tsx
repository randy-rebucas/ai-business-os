import Link from "next/link";

import { cn } from "@/lib/utils";

/** The platform mark: a report sheet (a heading rule and two lines) with a brass note key at its corner — every
 *  figure here has a note that leads to its evidence. Brass is the platform's, never the tenant's accent. */
export function Mark({ className, onDark }: { className?: string; onDark?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={cn("size-7", className)}>
      <rect x="2.5" y="3.5" width="15" height="18" rx="1" fill="none" stroke="currentColor" strokeWidth="2" />
      <rect x="6" y="7.5" width="8" height="2.75" fill="currentColor" />
      <rect x="6" y="12.75" width="5.5" height="1.5" fill="currentColor" opacity="0.55" />
      <rect x="6" y="16.25" width="7.5" height="1.5" fill="currentColor" opacity="0.55" />
      <circle cx="19.5" cy="4.5" r="3" fill={onDark ? "#c9a24a" : "var(--color-note)"} />
    </svg>
  );
}

export function Logo({ href = "/", className, inverted }: { href?: string; className?: string; inverted?: boolean }) {
  return (
    <Link
      href={href}
      className={cn("inline-flex items-center gap-2.5 font-display text-[17px] font-extrabold tracking-[-0.01em]",
        inverted ? "text-sidebar-fg" : "text-fg", className)}
    >
      <Mark onDark={inverted} />
      <span>AI Business OS</span>
    </Link>
  );
}
