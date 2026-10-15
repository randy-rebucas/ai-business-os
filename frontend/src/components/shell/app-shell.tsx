"use client";

import {
  Bell,
  Bot,
  Building2,
  CircleDollarSign,
  ClipboardCheck,
  FileBarChart,
  FileText,
  FlaskConical,
  FlaskRound,
  Gauge,
  Inbox,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  MessagesSquare,
  Receipt,
  Scale,
  ScrollText,
  Settings,
  Sparkles,
  Store,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Logo } from "@/components/brand/logo";
import { BrandingApplier, useBranding, useLogoSrc } from "@/lib/branding";
import { useOrgData } from "@/lib/hooks";
import { ROLE_LABEL } from "@/lib/labels";
import { useSession } from "@/lib/session";
import { cn, formatDateTime } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }>; perm?: string };

// Only features that exist are listed. Ordered by how often the owner needs them: the daily review first.
const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Daily review",
    items: [
      { href: "/app", label: "Overview", icon: LayoutDashboard },
      { href: "/app/control-center", label: "Control Center", icon: Gauge, perm: "task.read" },
      { href: "/app/approvals", label: "Approval inbox", icon: Inbox, perm: "agent.read" },
      { href: "/app/reports", label: "Daily reports", icon: FileBarChart, perm: "report.read" },
      { href: "/app/notifications", label: "Notifications", icon: Bell, perm: "notification.read" },
      { href: "/app/tasks", label: "Tasks & runs", icon: ListChecks, perm: "task.read" },
    ],
  },
  {
    group: "AI workforce",
    items: [
      { href: "/app/agents", label: "Agent directory", icon: Bot, perm: "agent.read" },
      { href: "/app/agents/team", label: "Build your team", icon: Users, perm: "agent.read" },
      { href: "/app/agents/catalog", label: "Agent catalog", icon: Store, perm: "agent.read" },
      { href: "/app/simulations", label: "Simulation & evaluation", icon: FlaskRound, perm: "agent.read" },
    ],
  },
  {
    group: "Governance",
    items: [
      { href: "/app/rules", label: "Business rules", icon: Scale, perm: "knowledge.read" },
      { href: "/app/usage", label: "Usage & costs", icon: CircleDollarSign, perm: "usage.read" },
      { href: "/app/audit", label: "Audit log", icon: ScrollText, perm: "audit.read" },
    ],
  },
  {
    group: "Knowledge",
    items: [
      { href: "/app/knowledge/ask", label: "Ask the knowledge base", icon: Sparkles, perm: "knowledge.ask" },
      { href: "/app/knowledge", label: "Documents", icon: FileText, perm: "knowledge.read" },
      { href: "/app/knowledge/evals", label: "Knowledge evaluation", icon: FlaskConical, perm: "knowledge.review" },
    ],
  },
  {
    group: "Company",
    items: [
      { href: "/app/records", label: "Business records", icon: Receipt, perm: "records.read" },
      { href: "/app/company", label: "Company profile", icon: Building2, perm: "company.read" },
      { href: "/app/onboarding", label: "Company setup", icon: ClipboardCheck, perm: "company.read" },
      { href: "/app/interview", label: "Business interview", icon: MessagesSquare, perm: "company.read" },
      { href: "/app/settings", label: "Settings", icon: Settings },
    ],
  },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { can } = useSession();
  const unread = useOrgData<{ unread: number }>(can("notification.read") ? "/api/v1/notifications/unread-count" : null,
    { refreshInterval: 30000 }).data?.unread ?? 0;
  // The most specific link wins, so /app/knowledge/ask doesn't also light up /app/knowledge.
  const activeHref = NAV.flatMap((g) => g.items)
    .map((i) => i.href)
    .filter((h) => pathname === h || (h !== "/app" && pathname.startsWith(`${h}/`)))
    .sort((a, b) => b.length - a.length)[0];
  const activeRef = useRef<HTMLAnchorElement | null>(null);
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [activeHref]);
  return (
    // The fade at the bottom says the list continues when it doesn't fit.
    <nav aria-label="Main" className="flex flex-1 flex-col gap-5 overflow-y-auto px-3 py-4 [mask-image:linear-gradient(to_bottom,#000_calc(100%-2.5rem),transparent)] [scrollbar-color:var(--color-sidebar-2)_transparent]">
      {NAV.map(({ group, items }) => {
        const visible = items.filter((i) => !i.perm || can(i.perm));
        if (!visible.length) return null;
        return (
          <div key={group}>
            <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-sidebar-muted">{group}</p>
            <ul className="space-y-px">
              {visible.map((item) => {
                const active = item.href === activeHref;
                return (
                  <li key={item.href}>
                    <Link
                      ref={active ? activeRef : undefined}
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-2.5 rounded-sm px-2 py-1.5 text-sm transition-colors",
                        active ? "bg-sidebar-2 font-semibold text-white" : "text-sidebar-fg/85 hover:bg-white/5 hover:text-white",
                      )}
                    >
                      <span aria-hidden className={cn("size-1.5 shrink-0", active ? "bg-sidebar-accent" : "bg-transparent")} />
                      <item.icon className={cn("size-4 shrink-0", active ? "text-sidebar-accent" : "text-sidebar-muted")} />
                      {item.label}
                      {item.href === "/app/notifications" && unread > 0 && (
                        <span className="ml-auto rounded-sm bg-white px-1.5 text-[11px] font-bold text-sidebar" aria-label={`${unread} unread`}>{unread}</span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
}

/** The tenant's identity in the platform's chrome: its own logo (on a white tile — logos are drawn for light
 *  grounds) or its initials on its brand marker colour. */
function Workspace() {
  const { me, orgId, switchOrg, membership } = useSession();
  const { data: branding } = useBranding();
  const logo = useLogoSrc(branding?.logo_url);
  const name = membership?.organization.name ?? "";
  return (
    <div className="mx-3 border-y border-white/10 py-3">
      <div className="flex items-center gap-3 px-1">
        {logo ? (
          // eslint-disable-next-line @next/next/no-img-element -- a blob: URL of the tenant's re-encoded PNG
          <img src={logo} alt={`${name} logo`} className="size-10 shrink-0 rounded-sm bg-white object-contain p-1" />
        ) : (
          <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-sm bg-white font-display text-sm font-extrabold text-sidebar">
            {initials(name) || "—"}
          </span>
        )}
        <div className="min-w-0">
          <p className="truncate font-semibold text-white">{name}</p>
          <p className="truncate text-xs text-sidebar-muted">
            {[branding?.industry, membership && ROLE_LABEL[membership.role]].filter(Boolean).join(" · ")}
          </p>
        </div>
      </div>
      {me.memberships.length > 1 && (
        <label className="mt-3 block px-1">
          <span className="sr-only">Active workspace</span>
          <select
            value={orgId ?? ""}
            onChange={(e) => switchOrg(e.target.value)}
            className="h-8 w-full rounded-sm border border-white/15 bg-white/5 px-2 text-sm text-sidebar-fg [&>option]:text-black"
          >
            {me.memberships.map((m) => (
              <option key={m.organization.id} value={m.organization.id}>
                {m.organization.name} ({ROLE_LABEL[m.role]})
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}

function UserFooter() {
  const { me, membership, logout } = useSession();
  return (
    <div className="border-t border-white/10 p-3">
      <div className="flex items-center gap-3 px-1">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-sidebar-fg">{me.user.full_name}</p>
          <p className="truncate text-xs text-sidebar-muted">
            {membership ? [membership.job_title, ROLE_LABEL[membership.role]].filter(Boolean).join(" · ") : "No workspace"}
          </p>
        </div>
        <button
          type="button"
          onClick={logout}
          className="rounded-sm p-2 text-sidebar-muted hover:bg-white/10 hover:text-white"
          aria-label="Sign out"
          title="Sign out"
        >
          <LogOut className="size-4" />
        </button>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const { me, membership, can } = useSession();

  const sidebar = (
    <>
      <div className="flex h-14 items-center border-b-2 border-[#c9a24a] px-4">
        <Logo href="/app" inverted />
      </div>
      {membership && <Workspace />}
      <NavLinks onNavigate={() => setOpen(false)} />
      <UserFooter />
    </>
  );

  return (
    <div className="flex min-h-dvh">
      {membership && <BrandingApplier key={membership.organization.id} />}
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col bg-sidebar lg:flex print:hidden">{sidebar}</aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <aside className="relative flex h-full w-72 flex-col bg-sidebar">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="absolute right-3 top-3.5 rounded-sm p-1.5 text-sidebar-muted hover:text-white"
              aria-label="Close navigation"
            >
              <X className="size-5" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 bg-sidebar px-4 lg:hidden print:hidden">
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="rounded-sm p-1.5 text-sidebar-fg hover:bg-white/10"
            aria-label="Open navigation"
          >
            <Menu className="size-5" />
          </button>
          <Logo href="/app" inverted />
        </header>
        {!me.user.email_verified_at && (
          <div className="border-b border-warning/30 bg-warning/10 px-6 py-2 text-xs text-warning print:hidden">
            Your email address is not verified yet.{" "}
            <Link href="/app/settings#account" className="underline underline-offset-2">
              Resend the link
            </Link>
          </div>
        )}
        {membership?.organization.deletion_scheduled_at && (
          <div role="status" className="border-b border-danger/30 bg-danger/10 px-6 py-2 text-xs text-danger print:hidden">
            This workspace is scheduled for permanent deletion on {formatDateTime(membership.organization.deletion_scheduled_at)}.{" "}
            <Link href="/app/settings#data" className="underline underline-offset-2">
              {can("org.delete") ? "Cancel or review" : "Details"}
            </Link>
          </div>
        )}
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 lg:px-10">
          {children}
        </main>
      </div>
    </div>
  );
}
