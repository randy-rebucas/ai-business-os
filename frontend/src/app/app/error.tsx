"use client";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/display";

// Next 16: error boundaries receive `retry` (not `reset`).
export default function AppError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <div className="mx-auto max-w-lg space-y-4 py-16">
      <Alert tone="danger" title="This page failed to load">
        {error.message || "Unexpected error."}
        {error.digest && <span className="ident mt-1 block text-xs">Reference: {error.digest}</span>}
      </Alert>
      <Button variant="secondary" onClick={retry}>
        Try again
      </Button>
    </div>
  );
}
