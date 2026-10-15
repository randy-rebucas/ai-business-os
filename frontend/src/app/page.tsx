import { ArrowRight } from "lucide-react";

import { Logo } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";

// The lifecycle, set like a report's contents page: the order is the order the work happens in.
const CONTENTS = [
  { title: "Describe your business", body: "What you sell, how you operate, who approves what, and your hours and budget.", part: "Setup" },
  { title: "Teach it your policies", body: "Upload SOPs and price lists; you review each one before any agent may use it.", part: "Knowledge" },
  { title: "Hire AI employees", body: "Finance, sales, support, operations and more — each with a written job, schedule and limits.", part: "Workforce" },
  { title: "Approve exactly what they may do", body: "You approve the configuration itself; any change comes back to you.", part: "Governance" },
  { title: "Test before trusting", body: "Every agent runs realistic scenarios in a sandbox — missing data, conflicting policies, injection attempts.", part: "Readiness" },
  { title: "Supervise with evidence", body: "Daily reports built from what actually ran, each figure traceable to its records.", part: "Reporting" },
];

// Behaviour the platform enforces in code and tests — not marketing claims.
const NEVER = [
  "A sensitive action happens before you approve its exact parameters.",
  "An outcome nobody could confirm is counted as done.",
  "A figure in a report comes from a model's memory instead of a record.",
  "A development adapter is shown without saying so.",
];

function ExampleSheet() {
  return (
    <figure className="rounded-sm border border-border border-t-[3px] border-t-rule bg-bg-2 p-6 shadow-[0_24px_48px_-28px_rgba(18,26,24,0.35)]">
      <p className="font-display text-lg font-bold">Finance and Accounting Agent — 15 October</p>
      <dl className="mt-4 grid grid-cols-2 border-t-2 border-rule">
        <div className="border-r border-border py-3 pr-4">
          <dt className="text-sm font-semibold">Actions completed</dt>
          <dd className="font-display text-[44px] font-extrabold leading-none tracking-[-0.02em]">
            12<span className="ml-1 align-super text-[13px] font-bold text-note">1</span>
          </dd>
        </div>
        <div className="py-3 pl-4">
          <dt className="text-sm font-semibold">Waiting for you</dt>
          <dd className="font-display text-[44px] font-extrabold leading-none tracking-[-0.02em] text-warning">
            1<span className="ml-1 align-super text-[13px] font-bold text-note">2</span>
          </dd>
        </div>
      </dl>
      <ol className="mt-3 divide-y divide-border border-t border-border text-sm">
        <li className="grid grid-cols-[1.25rem_1fr] gap-2 py-2"><span className="font-bold text-note">1</span>
          <span className="text-muted">Counted from 4 runs and 12 recorded tool calls: invoices read, reminders drafted, one discrepancy escalated.</span></li>
        <li className="grid grid-cols-[1.25rem_1fr] gap-2 py-2"><span className="font-bold text-note">2</span>
          <span className="text-muted">A payment reminder to a customer, held until you approve its exact text.</span></li>
      </ol>
      <figcaption className="mt-3 text-xs text-subtle">Example daily report — illustrative figures, not a real company.</figcaption>
    </figure>
  );
}

export default function Landing() {
  return (
    <div className="min-h-dvh bg-bg">
      <header className="bg-sidebar">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Logo inverted />
          <nav className="flex items-center gap-2">
            <ButtonLink href="/login" variant="ghost" size="sm" className="text-sidebar-fg hover:bg-white/10 hover:text-white">Sign in</ButtonLink>
            <ButtonLink href="/register" size="sm" className="bg-white text-sidebar hover:bg-sidebar-fg">Create workspace</ButtonLink>
          </nav>
        </div>
      </header>
      <main id="main">
        <section className="bg-sidebar pb-20 text-sidebar-fg">
          <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 pt-14 sm:px-6 lg:grid-cols-[1.15fr_1fr] lg:pt-20">
            <div>
              <h1 className="font-display text-[44px] font-extrabold leading-[1.02] tracking-[-0.025em] text-white sm:text-[64px]">
                AI employees you can audit.
              </h1>
              <p className="mt-6 max-w-xl text-lg text-sidebar-fg/90">
                Hire specialised AI agents, ground them in your own policies, test them before they act, approve exactly
                what they may do — and read every day what they did, with the records to prove it.
              </p>
              <div className="mt-9 flex flex-wrap gap-3">
                <ButtonLink href="/register" size="lg" className="bg-white text-sidebar hover:bg-sidebar-fg">Set up your company <ArrowRight /></ButtonLink>
                <ButtonLink href="/login" size="lg" variant="ghost" className="border border-white/30 text-white hover:bg-white/10 hover:text-white">Sign in</ButtonLink>
              </div>
            </div>
            <div className="text-fg lg:translate-y-14">
              <ExampleSheet />
            </div>
          </div>
        </section>

        <section aria-labelledby="contents" className="mx-auto max-w-6xl px-4 pb-16 pt-28 sm:px-6">
          <h2 id="contents" className="border-t-[3px] border-rule pt-4 font-display text-[28px] font-extrabold tracking-[-0.015em]">
            Contents: from onboarding to accountable work
          </h2>
          <ol className="mt-6">
            {CONTENTS.map((c, i) => (
              <li key={c.title} className="grid gap-x-6 gap-y-1 border-b border-border py-4 sm:grid-cols-[3rem_1fr_9rem] sm:items-baseline">
                <span className="font-display text-2xl font-extrabold text-note">{i + 1}</span>
                <div>
                  <h3 className="font-display text-lg font-bold">{c.title}</h3>
                  <p className="mt-0.5 text-muted">{c.body}</p>
                </div>
                <span className="text-sm font-semibold text-subtle sm:text-right">{c.part}</span>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="never" className="border-y border-border bg-bg-2">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[1fr_1.4fr]">
            <h2 id="never" className="font-display text-[28px] font-extrabold leading-tight tracking-[-0.015em]">
              What the platform never lets happen
            </h2>
            <ul className="divide-y divide-border border-t-2 border-rule">
              {NEVER.map((n) => (
                <li key={n} className="py-3.5 text-lg">{n}</li>
              ))}
            </ul>
          </div>
        </section>
      </main>
      <footer>
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-xs text-subtle sm:px-6">
          <span>© {new Date().getFullYear()} AI Business OS</span>
          <span>Built for small and growing businesses in the Philippines.</span>
        </div>
      </footer>
    </div>
  );
}
