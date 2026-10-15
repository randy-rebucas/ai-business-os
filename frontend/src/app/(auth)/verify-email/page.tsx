"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { Alert, Spinner } from "@/components/ui/display";
import { api, ApiError } from "@/lib/api";

function Verify() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<"working" | "done" | "failed">(token ? "working" : "failed");
  const [message, setMessage] = useState("This verification link is missing its token.");
  const sent = useRef(false); // tokens are single-use: never post twice (React strict mode runs effects twice)

  useEffect(() => {
    if (!token || sent.current) return;
    sent.current = true;
    api("/api/v1/auth/verify-email", { method: "POST", body: { token } })
      .then(() => setState("done"))
      .catch((err) => {
        setMessage(err instanceof ApiError ? err.message : "Verification failed.");
        setState("failed");
      });
  }, [token]);

  if (state === "working") return <Spinner label="Verifying your email" />;
  return (
    <div className="space-y-4">
      {state === "done" ? (
        <Alert tone="success" title="Email verified">
          Thanks — your address is confirmed.
        </Alert>
      ) : (
        <Alert tone="danger" title="Could not verify">
          {message}
        </Alert>
      )}
      <Link href="/app" className="block text-center text-sm text-accent underline underline-offset-2">
        Go to your workspace
      </Link>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <Verify />
    </Suspense>
  );
}
