import { Logo, Mark } from "@/components/brand/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-sidebar p-12 text-sidebar-fg lg:flex">
        <Logo inverted />
        <div className="max-w-md">
          <p className="font-display text-[34px] font-extrabold leading-[1.1] tracking-[-0.015em] text-white">
            Every figure your AI employees report comes with a note that leads to its evidence.
          </p>
          <p className="mt-4 text-sidebar-muted">
            Runs, tool calls and approvals are recorded as they happen, and reports are built from those records — never
            from a model&apos;s memory.
          </p>
        </div>
        <span aria-hidden className="absolute -bottom-20 -right-20 opacity-[0.07]"><Mark onDark className="size-96 text-white" /></span>
        <p className="text-xs text-sidebar-muted">AI Business OS</p>
      </aside>
      <div className="flex flex-col items-center justify-center bg-bg px-4 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <Logo />
          </div>
          <main id="main" className="rounded-sm border border-border border-t-[3px] border-t-rule bg-bg-2 p-6">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
