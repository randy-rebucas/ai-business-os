"use client";

import { SWRConfig } from "swr";

import { AppShell } from "@/components/shell/app-shell";
import { Spinner } from "@/components/ui/display";
import { swrFetcher } from "@/lib/api";
import { SessionProvider } from "@/lib/session";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={{ fetcher: swrFetcher, revalidateOnFocus: false }}>
      <SessionProvider
        fallback={
          <div className="grid min-h-dvh place-items-center">
            <Spinner label="Loading workspace" />
          </div>
        }
      >
        <AppShell>{children}</AppShell>
      </SessionProvider>
    </SWRConfig>
  );
}
