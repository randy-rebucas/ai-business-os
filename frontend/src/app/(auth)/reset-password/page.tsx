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

const schema = z
  .object({
    new_password: z.string().min(10, "Use at least 10 characters").max(128),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Passwords don't match" });
type Values = z.infer<typeof schema>;

function ResetForm() {
  const router = useRouter();
  const token = useSearchParams().get("token");
  const [formError, setFormError] = useState<string | null>(null);
  const { register, handleSubmit, setError, formState } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async ({ new_password }) => {
    setFormError(null);
    try {
      await api("/api/v1/auth/password-reset/confirm", { method: "POST", body: { token, new_password } });
      router.replace("/login?reset=1");
    } catch (err) {
      setFormError(applyApiError(err, setError));
    }
  });

  if (!token) {
    return (
      <Alert tone="danger" title="Missing reset token">
        Open the link from your email again, or{" "}
        <Link href="/forgot-password" className="underline">
          request a new one
        </Link>
        .
      </Alert>
    );
  }
  return (
    <>
      <h1 className="text-lg font-semibold">Choose a new password</h1>
      <p className="mt-1 text-sm text-muted">This signs you out everywhere else.</p>
      <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
        {formError && <Alert tone="danger">{formError}</Alert>}
        <Field label="New password" error={formState.errors.new_password?.message}>
          {(p) => <Input type="password" autoComplete="new-password" {...p} {...register("new_password")} />}
        </Field>
        <Field label="Confirm password" error={formState.errors.confirm?.message}>
          {(p) => <Input type="password" autoComplete="new-password" {...p} {...register("confirm")} />}
        </Field>
        <Button type="submit" className="w-full" loading={formState.isSubmitting}>
          Update password
        </Button>
      </form>
    </>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetForm />
    </Suspense>
  );
}
