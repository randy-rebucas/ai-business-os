import { ButtonLink } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main id="main" className="grid min-h-dvh place-items-center px-4">
      <div className="text-center">
        <p className="text-sm font-medium text-accent">404</p>
        <h1 className="mt-2 text-2xl font-semibold">Page not found</h1>
        <p className="mt-2 text-sm text-muted">The page you are looking for doesn&apos;t exist or has moved.</p>
        <ButtonLink href="/app" className="mt-6">Go to your workspace</ButtonLink>
      </div>
    </main>
  );
}
