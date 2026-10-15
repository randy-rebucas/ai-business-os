"use client";

import { Plus, Receipt, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/form";
import { Tabs } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { INVOICE_STATE, money, totals } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { Draft, Expense, Invoice, Receivables } from "@/lib/types";
import { formatDate, formatDateTime } from "@/lib/utils";

const today = () => new Date().toISOString().slice(0, 10);
type Line = { description: string; quantity: string; unit_price: string };

function useAction(after: () => Promise<unknown>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await after();
      return true;
    } catch (err) {
      setError(errorMessage(err));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

function NewInvoice({ onDone }: { onDone: () => Promise<unknown> }) {
  const empty = { number: "", customer_name: "", customer_email: "", currency: "USD", issue_date: today(), due_date: today() };
  const [f, setF] = useState(empty);
  const [lines, setLines] = useState<Line[]>([{ description: "", quantity: "1", unit_price: "" }]);
  const { busy, error, run } = useAction(onDone);
  const set = (k: keyof typeof empty) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const setLine = (i: number, k: keyof Line, v: string) => setLines(lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await run(() => api("/api/v1/business/invoices", { method: "POST", org: true,
      body: { ...f, customer_email: f.customer_email || null, lines } }));
    if (ok) { setF(empty); setLines([{ description: "", quantity: "1", unit_price: "" }]); }
  };
  return (
    <Card>
      <CardHeader title="Record an invoice" description="The total is calculated from the lines (exact decimals, rounded to cents)." />
      <form onSubmit={submit} className="space-y-4 px-5 py-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Invoice number">{(p) => <Input {...p} required maxLength={40} value={f.number} onChange={set("number")} />}</Field>
          <Field label="Customer">{(p) => <Input {...p} required maxLength={200} value={f.customer_name} onChange={set("customer_name")} />}</Field>
          <Field label="Customer email" hint="Used for payment reminders">{(p) => <Input {...p} type="email" value={f.customer_email} onChange={set("customer_email")} />}</Field>
          <Field label="Currency">{(p) => <Input {...p} required pattern="[A-Za-z]{3}" maxLength={3} value={f.currency} onChange={set("currency")} />}</Field>
          <Field label="Issue date">{(p) => <Input {...p} type="date" required value={f.issue_date} onChange={set("issue_date")} />}</Field>
          <Field label="Due date">{(p) => <Input {...p} type="date" required value={f.due_date} onChange={set("due_date")} />}</Field>
        </div>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Lines</legend>
          {lines.map((l, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[1fr_6rem_8rem_auto]">
              <Field label={`Line ${i + 1} description`}>{(p) => <Input {...p} required value={l.description} onChange={(e) => setLine(i, "description", e.target.value)} />}</Field>
              <Field label="Quantity">{(p) => <Input {...p} required inputMode="decimal" value={l.quantity} onChange={(e) => setLine(i, "quantity", e.target.value)} />}</Field>
              <Field label="Unit price">{(p) => <Input {...p} required inputMode="decimal" value={l.unit_price} onChange={(e) => setLine(i, "unit_price", e.target.value)} />}</Field>
              <div className="flex items-end">
                {lines.length > 1 && <Button variant="ghost" size="icon" aria-label={`Remove line ${i + 1}`} onClick={() => setLines(lines.filter((_, j) => j !== i))}><Trash2 /></Button>}
              </div>
            </div>
          ))}
          <Button variant="secondary" size="sm" onClick={() => setLines([...lines, { description: "", quantity: "1", unit_price: "" }])}><Plus /> Add line</Button>
        </fieldset>
        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" loading={busy}>Record invoice</Button>
      </form>
    </Card>
  );
}

function PaymentForm({ inv, onDone }: { inv: Invoice; onDone: () => Promise<unknown> }) {
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [received, setReceived] = useState(today());
  const { busy, error, run } = useAction(onDone);
  return (
    <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={async (e) => {
      e.preventDefault();
      if (await run(() => api(`/api/v1/business/invoices/${inv.id}/payments`, { method: "POST", org: true,
        body: { amount, received_on: received, reference: reference || null } }))) { setAmount(""); setReference(""); }
    }}>
      <Field label={`Payment (${inv.currency})`} className="w-36">{(p) => <Input {...p} required inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />}</Field>
      <Field label="Received" className="w-40">{(p) => <Input {...p} type="date" required value={received} onChange={(e) => setReceived(e.target.value)} />}</Field>
      <Field label="Bank reference" className="w-44">{(p) => <Input {...p} maxLength={100} value={reference} onChange={(e) => setReference(e.target.value)} />}</Field>
      <Button type="submit" size="sm" loading={busy}>Record payment</Button>
      {error && <Alert tone="danger" className="w-full">{error}</Alert>}
    </form>
  );
}

function Invoices() {
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const invoices = useOrgData<Invoice[]>("/api/v1/business/invoices");
  const rec = useOrgData<Receivables>("/api/v1/business/receivables");
  const refresh = () => Promise.all(["/api/v1/business/invoices", "/api/v1/business/receivables"].map((p) => mutate([p, orgId])));
  if (invoices.error) return <ErrorState error={invoices.error} />;
  if (!invoices.data) return <Spinner />;
  return (
    <div className="space-y-6">
      {rec.data && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Card className="px-5 py-4"><p className="text-xs text-muted">Outstanding</p><p className="mt-1 text-lg font-semibold">{totals(rec.data.outstanding_by_currency)}</p></Card>
          <Card className="px-5 py-4"><p className="text-xs text-muted">Overdue (as of {formatDate(rec.data.as_of)})</p><p className="mt-1 text-lg font-semibold">{totals(rec.data.overdue_by_currency)}</p></Card>
          <Card className="px-5 py-4"><p className="text-xs text-muted">Invoices</p><p className="mt-1 text-sm">{rec.data.counts.open} open · {rec.data.counts.overdue} overdue · {rec.data.counts.paid} paid</p></Card>
        </div>
      )}
      {can("records.manage") && <NewInvoice onDone={refresh} />}
      {invoices.data.length === 0 ? (
        <EmptyState icon={Receipt} title="No invoices yet">Record invoices here; the Finance agent reads them through its registered tools.</EmptyState>
      ) : (
        <Table label="Invoices">
          <thead><tr><th className={th}>Invoice</th><th className={th}>Customer</th><th className={th}>Due</th><th className={th}>Total</th><th className={th}>Balance</th><th className={th}>State</th></tr></thead>
          <tbody>
            {invoices.data.map((inv) => (
              <tr key={inv.id}>
                <td className={td}>
                  <details>
                    <summary className="cursor-pointer font-medium">{inv.number}</summary>
                    <ul className="mt-2 space-y-0.5 text-xs text-muted">
                      {inv.lines.map((l) => <li key={l.id}>{l.description}: {l.quantity} × {l.unit_price} = {l.amount}</li>)}
                      {inv.payments.map((p) => <li key={p.id}>Paid {money(p.amount, p.currency)} on {formatDate(p.received_on)}{p.reference && ` (${p.reference})`}</li>)}
                    </ul>
                    {can("records.manage") && ["open", "overdue"].includes(inv.state) && <PaymentForm inv={inv} onDone={refresh} />}
                  </details>
                </td>
                <td className={td}>{inv.customer_name}<div className="text-xs text-muted">{inv.customer_email ?? "no email"}</div></td>
                <td className={td}>{formatDate(inv.due_date)}{inv.days_overdue > 0 && <div className="text-xs text-warning">{inv.days_overdue} days overdue</div>}</td>
                <td className={td}>{money(inv.total, inv.currency)}</td>
                <td className={td}>{money(inv.balance, inv.currency)}</td>
                <td className={td}><Badge tone={INVOICE_STATE[inv.state].tone}>{INVOICE_STATE[inv.state].label}</Badge>
                  {inv.checks.map((c) => <p key={c} className="mt-1 max-w-xs text-xs text-danger">{c}</p>)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}

function Expenses() {
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const expenses = useOrgData<Expense[]>("/api/v1/business/expenses");
  const empty = { incurred_on: today(), supplier: "", description: "", amount: "", currency: "USD" };
  const [f, setF] = useState(empty);
  const { busy, error, run } = useAction(() => mutate(["/api/v1/business/expenses", orgId]));
  const set = (k: keyof typeof empty) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  if (expenses.error) return <ErrorState error={expenses.error} />;
  if (!expenses.data) return <Spinner />;
  return (
    <div className="space-y-6">
      {can("records.manage") && (
        <Card>
          <CardHeader title="Submit an expense" description="Submitting starts the Finance agent's categorisation task when it is active." />
          <form className="grid gap-3 px-5 py-4 sm:grid-cols-5" onSubmit={async (e) => {
            e.preventDefault();
            if (await run(() => api("/api/v1/business/expenses", { method: "POST", org: true, body: f }))) setF(empty);
          }}>
            <Field label="Date">{(p) => <Input {...p} type="date" required value={f.incurred_on} onChange={set("incurred_on")} />}</Field>
            <Field label="Supplier">{(p) => <Input {...p} required value={f.supplier} onChange={set("supplier")} />}</Field>
            <Field label="Description">{(p) => <Input {...p} required value={f.description} onChange={set("description")} />}</Field>
            <Field label="Amount">{(p) => <Input {...p} required inputMode="decimal" value={f.amount} onChange={set("amount")} />}</Field>
            <Field label="Currency">{(p) => <Input {...p} required maxLength={3} value={f.currency} onChange={set("currency")} />}</Field>
            <div className="sm:col-span-5">{error && <Alert tone="danger" className="mb-3">{error}</Alert>}<Button type="submit" loading={busy}>Submit expense</Button></div>
          </form>
        </Card>
      )}
      {expenses.data.length === 0 ? <p className="text-sm text-muted">No expenses yet.</p> : (
        <Table label="Expenses">
          <thead><tr><th className={th}>Date</th><th className={th}>Supplier</th><th className={th}>Description</th><th className={th}>Amount</th><th className={th}>Status</th></tr></thead>
          <tbody>
            {expenses.data.map((e) => (
              <tr key={e.id}>
                <td className={td}>{formatDate(e.incurred_on)}</td><td className={td}>{e.supplier}</td><td className={td}>{e.description}</td>
                <td className={td}>{money(e.amount, e.currency)}</td><td className={td}>{e.status}{e.category && ` · ${e.category}`}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}

function Drafts() {
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const drafts = useOrgData<Draft[]>("/api/v1/business/drafts");
  const { busy, error, run } = useAction(() => mutate(["/api/v1/business/drafts", orgId]));
  if (drafts.error) return <ErrorState error={drafts.error} />;
  if (!drafts.data) return <Spinner />;
  if (drafts.data.length === 0) return <p className="text-sm text-muted">No drafts yet. Agents prepare drafts here; drafting never sends anything.</p>;
  return (
    <div className="space-y-3">
      {error && <Alert tone="danger">{error}</Alert>}
      {drafts.data.map((d) => (
        <Card key={d.id} className="px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-medium">{d.subject} <Badge tone={d.status === "sent" ? "success" : d.status === "draft" ? "info" : "neutral"}>{d.status}</Badge></p>
            <span className="text-xs text-muted">{d.recipient ? `To ${d.recipient} · ` : ""}{formatDateTime(d.created_at)}
              {d.run_id && <> · <Link href={`/app/tasks/${d.run_id}`} className="text-accent underline underline-offset-2">from this run</Link></>}</span>
          </div>
          <p className="mt-2 whitespace-pre-line text-sm text-muted">{d.body}</p>
          {d.status === "draft" && can("records.manage") && (
            <Button size="sm" variant="secondary" className="mt-3" loading={busy} onClick={() => run(() => api(`/api/v1/business/drafts/${d.id}/discard`, { method: "POST", org: true }))}>Discard</Button>
          )}
        </Card>
      ))}
    </div>
  );
}

export default function RecordsPage() {
  return (
    <>
      <PageHeader title="Business records"
        description="The authoritative records agents work from. People record them here; agents only read them and prepare drafts, through registered tools." />
      <Tabs label="Record types" items={[
        { key: "invoices", label: "Invoices & receivables", content: <Invoices /> },
        { key: "expenses", label: "Expenses", content: <Expenses /> },
        { key: "drafts", label: "Drafts", content: <Drafts /> },
      ]} />
    </>
  );
}
