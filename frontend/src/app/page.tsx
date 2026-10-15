import { ArrowRight, BookOpenCheck, ClipboardCheck, FlaskConical, ShieldCheck, UserPlus, Workflow } from "lucide-react";

import { Logo } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";

const LIFECYCLE = [
  { icon: ClipboardCheck, title: "Describe your business", body: "A guided profile of what you sell, how you operate, who approves what, and what success looks like." },
  { icon: UserPlus, title: "Hire AI employees", body: "Finance, sales, support, operations and more — each with a written job description, schedule and limits." },
  { icon: BookOpenCheck, title: "Teach them your policies", body: "Upload SOPs, price lists and handbooks. Agents answer from your approved documents, with citations." },
  { icon: FlaskConical, title: "Test before trusting", body: "Every agent runs realistic scenarios — missing data, conflicting policies, injection attempts — before activation." },
  { icon: ShieldCheck, title: "Approve every permission", body: "Sensitive actions need your sign-off, enforced on the server and bound to the exact action you approved." },
  { icon: Workflow, title: "Supervise with evidence", body: "Daily reports built from execution records, not the model's memory — every claim traceable to its source." },
];

export default function Landing() {
  return (
    <div className="min-h-dvh bg-bg">
      <header className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Logo />
        <nav className="flex items-center gap-2">
          <ButtonLink href="/login" variant="ghost" size="sm">Sign in</ButtonLink>
          <ButtonLink href="/register" size="sm">Create workspace</ButtonLink>
        </nav>
      </header>
      <main id="main">
        <section className="mx-auto max-w-6xl px-4 pb-16 pt-16 sm:px-6 sm:pt-24">
          <p className="text-sm font-medium text-accent">The operating system for an AI workforce</p>
          <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight text-fg sm:text-5xl">
            Run your company with AI employees you can actually supervise.
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-muted">
            Onboard your business, hire specialised AI agents, ground them in your own policies, test them against real
            scenarios, and approve exactly what they may do — then review verifiable reports of their work.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href="/register" size="lg">Set up your company <ArrowRight /></ButtonLink>
            <ButtonLink href="/login" size="lg" variant="secondary">Sign in</ButtonLink>
          </div>
        </section>
        <section aria-labelledby="lifecycle" className="border-t border-border bg-bg-2">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <h2 id="lifecycle" className="text-xl font-semibold tracking-tight">From onboarding to accountable work</h2>
            <ol className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {LIFECYCLE.map((step, i) => (
                <li key={step.title} className="rounded-lg border border-border bg-bg p-5">
                  <div className="flex items-center gap-3">
                    <span className="grid size-9 place-items-center rounded-md bg-accent-soft text-accent">
                      <step.icon className="size-4" aria-hidden />
                    </span>
                    <span className="text-xs font-medium text-subtle">Step {i + 1}</span>
                  </div>
                  <h3 className="mt-4 font-semibold text-fg">{step.title}</h3>
                  <p className="mt-1.5 text-sm text-muted">{step.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>
      </main>
      <footer className="border-t border-border">
        <div className="mx-auto max-w-6xl px-4 py-6 text-xs text-subtle sm:px-6">© {new Date().getFullYear()} AI Business OS</div>
      </footer>
    </div>
  );
}
