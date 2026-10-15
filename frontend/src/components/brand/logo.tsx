import Link from "next/link";

import { cn } from "@/lib/utils";

export function Mark({ className }: { className?: string }) {
  // Four tiles = a small team; the accent tile is the coordinator.
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={cn("size-7", className)}>
      <rect x="2" y="2" width="9" height="9" rx="2" className="fill-accent" />
      <rect x="13" y="2" width="9" height="9" rx="2" className="fill-current opacity-35" />
      <rect x="2" y="13" width="9" height="9" rx="2" className="fill-current opacity-35" />
      <rect x="13" y="13" width="9" height="9" rx="2" className="fill-current opacity-60" />
    </svg>
  );
}

export function Logo({ href = "/", className, inverted }: { href?: string; className?: string; inverted?: boolean }) {
  return (
    <Link
      href={href}
      className={cn("inline-flex items-center gap-2.5 font-semibold tracking-tight", inverted ? "text-sidebar-fg" : "text-fg", className)}
    >
      <Mark className={inverted ? "[&_.fill-accent]:fill-sidebar-accent" : undefined} />
      <span>
        AI Business <span className={inverted ? "text-sidebar-accent" : "text-accent"}>OS</span>
      </span>
    </Link>
  );
}
