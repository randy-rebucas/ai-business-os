"use client";

import {
  Bell,
  Bot,
  CircleDollarSign,
  FileBarChart,
  Gauge,
  Building2,
  ClipboardCheck,
  FileText,
  FlaskConical,
  FlaskRound,
  Inbox,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Receipt,
  MessagesSquare,
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
import { useState } from "react";

import { Logo } from "@/components/brand/logo";
import { useOrgData } from "@/lib/hooks";
import { ROLE_LABEL } from "@/lib/labels";
import { useSession } from "@/lib/session";
import { cn, formatDateTime } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }>; perm?: string };

// Only features that exist are listed.
const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Workspace",
    items: [
      { href: "/app", label: "Overview", icon: LayoutDashboard },
      { href: "/app/onboarding", label: "Company setup", icon: ClipboardCheck, perm: "company.read" },
      { href: "/app/company", label: "Company profile", icon: Building2, perm: "company.read" },
      { href: "/app/interview", label: "Business interview", icon: MessagesSquare, perm: "company.read" },
      { href: "/app/records", label: "Business records", icon: Receipt, perm: "records.read" },
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
    group: "AI workforce",
    items: [
      { href: "/app/agents", label: "Agent directory", icon: Bot, perm: "agent.read" },
      { href: "/app/tasks", label: "Tasks & runs", icon: ListChecks, perm: "task.read" },
      { href: "/app/agents/team", label: "Build your team", icon: Users, perm: "agent.read" },
      { href: "/app/agents/catalog", label: "Agent catalog", icon: Store, perm: "agent.read" },
      { href: "/app/simulations", label: "Simulation & evaluation", icon: FlaskRound, perm: "agent.read" },
    ],
  },
  {
    group: "Reporting",
    items: [
      { href: "/app/control-center", label: "Control Center", icon: Gauge, perm: "task.read" },
      { href: "/app/reports", label: "Daily reports", icon: FileBarChart, perm: "report.read" },
      { href: "/app/notifications", label: "Notifications", icon: Bell, perm: "notification.read" },
      { href: "/app/usage", label: "Usage & costs", icon: CircleDollarSign, perm: "usage.read" },
    ],
  },
  {
    group: "Governance",
    items: [
      { href: "/app/approvals", label: "Approval inbox", icon: Inbox, perm: "agent.read" },
      { href: "/app/rules", label: "Business rules", icon: Scale, perm: "knowledge.read" },
      { href: "/app/audit", label: "Audit log", icon: ScrollText, perm: "audit.read" },
    ],
  },
  { group: "Admin", items: [{ href: "/app/settings", label: "Settings", icon: Settings }] },
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
  return (
    <nav aria-label="Main" className="flex flex-1 flex-col gap-5 overflow-y-auto px-3 py-4">
      {NAV.map(({ group, items }) => {
        const visible = items.filter((i) => !i.perm || can(i.perm));
        if (!visible.length) return null;
        return (
          <div key={group}>
            <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-sidebar-muted">{group}</p>
            <ul className="space-y-0.5">
              {visible.map((item) => {
                const active = item.href === activeHref;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                        active
                          ? "bg-white/10 text-sidebar-fg"
                          : "text-sidebar-muted hover:bg-white/5 hover:text-sidebar-fg",
                      )}
                    >
                      <item.icon className={cn("size-4", active && "text-sidebar-accent")} />
                      {item.label}
                      {item.href === "/app/notifications" && unread > 0 && (
                        <span className="ml-auto rounded-full bg-sidebar-accent px-1.5 text-[11px] font-semibold text-sidebar" aria-label={`${unread} unread`}>{unread}</span>
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

function OrgSwitcher() {
  const { me, orgId, switchOrg, membership } = useSession();
  if (me.memberships.length <= 1) {
    return (
      <div className="flex items-center gap-2 px-3 text-sm">
        <Building2 className="size-4 text-sidebar-muted" aria-hidden />
        <span className="truncate text-sidebar-fg">{membership?.organization.name}</span>
      </div>
    );
  }
  return (
    <label className="block px-3">
      <span className="sr-only">Active workspace</span>
      <select
        value={orgId ?? ""}
        onChange={(e) => switchOrg(e.target.value)}
        className="h-9 w-full rounded-md border border-white/15 bg-white/5 px-2 text-sm text-sidebar-fg [&>option]:text-black"
      >
        {me.memberships.map((m) => (
          <option key={m.organization.id} value={m.organization.id}>
            {m.organization.name} ({ROLE_LABEL[m.role]})
          </option>
        ))}
      </select>
    </label>
  );
}

function UserFooter() {
  const { me, membership, logout } = useSession();
  return (
    <div className="border-t border-white/10 p-3">
      <div className="flex items-center gap-3 px-1">
        <div
          aria-hidden
          className="grid size-8 shrink-0 place-items-center rounded-full bg-white/10 text-xs font-semibold text-sidebar-fg"
        >
          {me.user.full_name.slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm text-sidebar-fg">{me.user.full_name}</p>
          <p className="truncate text-xs text-sidebar-muted">
            {membership ? [membership.job_title, ROLE_LABEL[membership.role]].filter(Boolean).join(" · ") : "No workspace"}
          </p>
        </div>
        <button
          type="button"
          onClick={logout}
          className="rounded-md p-2 text-sidebar-muted hover:bg-white/10 hover:text-sidebar-fg"
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
      <div className="flex h-14 items-center border-b border-white/10 px-4">
        <Logo href="/app" inverted />
      </div>
      <div className="pt-4">
        <OrgSwitcher />
      </div>
      <NavLinks onNavigate={() => setOpen(false)} />
      <UserFooter />
    </>
  );

  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col bg-sidebar lg:flex print:hidden">{sidebar}</aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <aside className="relative flex h-full w-72 flex-col bg-sidebar">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="absolute right-3 top-3.5 rounded-md p-1.5 text-sidebar-muted hover:text-sidebar-fg"
              aria-label="Close navigation"
            >
              <X className="size-5" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-border bg-bg-2 px-4 lg:hidden print:hidden">
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="rounded-md p-1.5 text-muted hover:text-fg"
            aria-label="Open navigation"
          >
            <Menu className="size-5" />
          </button>
          <Logo href="/app" />
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
