import { Logo } from "@/components/brand/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh place-items-center bg-bg px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Logo />
        </div>
        <main id="main" className="rounded-lg border border-border bg-bg-2 p-6 shadow-sm">
          {children}
        </main>
      </div>
    </div>
  );
}
