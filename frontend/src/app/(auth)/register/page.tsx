"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api";
import { applyApiError, blankToNull } from "@/lib/forms";

const schema = z.object({
  full_name: z.string().trim().min(1, "Enter your name").max(200),
  job_title: z.string().trim().max(120),
  organization_name: z.string().trim().min(1, "Enter your company name").max(200),
  email: z.string().trim().email("Enter a valid email address"),
  password: z.string().min(10, "Use at least 10 characters").max(128),
});
type Values = z.infer<typeof schema>;

export default function RegisterPage() {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const { register, handleSubmit, setError, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { job_title: "CEO" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await api("/api/v1/auth/register", { method: "POST", body: blankToNull(values) });
      router.replace("/app/onboarding");
    } catch (err) {
      setFormError(applyApiError(err, setError));
    }
  });

  return (
    <>
      <h1 className="text-lg font-semibold">Create your company workspace</h1>
      <p className="mt-1 text-sm text-muted">You&apos;ll be the workspace owner. Your job title is just a label.</p>
      <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
        {formError && <Alert tone="danger">{formError}</Alert>}
        <Field label="Your name" error={formState.errors.full_name?.message}>
          {(p) => <Input autoComplete="name" {...p} {...register("full_name")} />}
        </Field>
        <Field label="Your title" error={formState.errors.job_title?.message} hint="Optional, e.g. CEO or Founder.">
          {(p) => <Input autoComplete="organization-title" {...p} {...register("job_title")} />}
        </Field>
        <Field label="Company name" error={formState.errors.organization_name?.message}>
          {(p) => <Input autoComplete="organization" {...p} {...register("organization_name")} />}
        </Field>
        <Field label="Work email" error={formState.errors.email?.message}>
          {(p) => <Input type="email" autoComplete="email" {...p} {...register("email")} />}
        </Field>
        <Field label="Password" error={formState.errors.password?.message} hint="At least 10 characters.">
          {(p) => <Input type="password" autoComplete="new-password" {...p} {...register("password")} />}
        </Field>
        <Button type="submit" className="w-full" loading={formState.isSubmitting}>
          Create workspace
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-accent underline underline-offset-2">
          Sign in
        </Link>
      </p>
    </>
  );
}
