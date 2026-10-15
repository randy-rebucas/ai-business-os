"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api";
import { applyApiError } from "@/lib/forms";

const schema = z.object({
  email: z.string().trim().email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});
type Values = z.infer<typeof schema>;

/** Only same-site relative paths are followed after sign-in (no open redirects). */
function safeNext(next: string | null): string {
  return next && next.startsWith("/app") && !next.startsWith("//") ? next : "/app";
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [formError, setFormError] = useState<string | null>(null);
  const { register, handleSubmit, setError, formState } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await api("/api/v1/auth/login", { method: "POST", body: values });
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      setFormError(applyApiError(err, setError));
    }
  });

  return (
    <>
      <h1 className="text-lg font-semibold">Sign in</h1>
      <p className="mt-1 text-sm text-muted">Welcome back to your AI workforce.</p>
      <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
        {params.get("reset") === "1" && <Alert tone="success">Password updated. Sign in with your new password.</Alert>}
        {formError && <Alert tone="danger">{formError}</Alert>}
        <Field label="Email" error={formState.errors.email?.message}>
          {(p) => <Input type="email" autoComplete="email" {...p} {...register("email")} />}
        </Field>
        <Field label="Password" error={formState.errors.password?.message}>
          {(p) => <Input type="password" autoComplete="current-password" {...p} {...register("password")} />}
        </Field>
        <div className="flex justify-end">
          <Link href="/forgot-password" className="text-sm text-accent underline-offset-2 hover:underline">
            Forgot password?
          </Link>
        </div>
        <Button type="submit" className="w-full" loading={formState.isSubmitting}>
          Sign in
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        New here?{" "}
        <Link href="/register" className="text-accent underline underline-offset-2">
          Create a workspace
        </Link>
      </p>
    </>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
