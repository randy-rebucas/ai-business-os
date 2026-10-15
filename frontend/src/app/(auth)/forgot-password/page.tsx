"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api";
import { applyApiError } from "@/lib/forms";

const schema = z.object({ email: z.string().trim().email("Enter a valid email address") });
type Values = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const { register, handleSubmit, setError, formState } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await api("/api/v1/auth/password-reset/request", { method: "POST", body: values });
      setSent(true);
    } catch (err) {
      setFormError(applyApiError(err, setError));
    }
  });

  return (
    <>
      <h1 className="text-lg font-semibold">Reset your password</h1>
      {sent ? (
        <Alert tone="success" className="mt-6">
          If an account exists for that email, a reset link is on its way. It expires in 30 minutes.
        </Alert>
      ) : (
        <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
          {formError && <Alert tone="danger">{formError}</Alert>}
          <Field label="Email" error={formState.errors.email?.message}>
            {(p) => <Input type="email" autoComplete="email" {...p} {...register("email")} />}
          </Field>
          <Button type="submit" className="w-full" loading={formState.isSubmitting}>
            Send reset link
          </Button>
        </form>
      )}
      <p className="mt-6 text-center text-sm text-muted">
        <Link href="/login" className="text-accent underline underline-offset-2">
          Back to sign in
        </Link>
      </p>
    </>
  );
}
