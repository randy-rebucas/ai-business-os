import type { Metadata } from "next";
import { connection } from "next/server";

import { fontVariables } from "@/lib/fonts";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "AI Business OS", template: "%s · AI Business OS" },
  description: "Hire, train, test and supervise an AI workforce grounded in your company's own knowledge.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Every page renders per request so Next can tag its scripts with the CSP nonce from src/proxy.ts.
  await connection();
  return (
    <html lang="en" className={fontVariables}>
      <body className="min-h-dvh">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-accent-fill focus:px-3 focus:py-2 focus:text-on-accent-fill"
        >
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
