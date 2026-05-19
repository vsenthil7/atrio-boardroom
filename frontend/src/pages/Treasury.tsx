import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  authoriseProposal,
  listProposals,
  proposeTreasury,
  rejectProposal,
} from "@/api/treasury";
import { getActiveMandate } from "@/api/extras";
import { listSessions } from "@/api/sessions";
import { apiErrorMessage } from "@/api/client";
import { useAuthStore } from "@/store/auth";
import type { TreasuryProposal } from "@/types";

export function TreasuryPage(): JSX.Element {
  const user = useAuthStore((s) => s.user);
  const qc = useQueryClient();
  const mandate = useQuery({ queryKey: ["mandate", "active"], queryFn: getActiveMandate, retry: false });
  const proposals = useQuery({ queryKey: ["proposals"], queryFn: () => listProposals() });
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: listSessions });

  const [form, setForm] = useState({
    session_id: "",
    instrument: "SHV-xStock",
    side: "buy" as "buy" | "sell",
    qty: "10",
    expected_price: "",
  });
  const [error, setError] = useState<string | null>(null);

  const propose = useMutation({
    mutationFn: proposeTreasury,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["proposals"] });
      setError(null);
    },
    onError: (e) => setError(apiErrorMessage(e)),
  });

  return (
    <div className="max-w-7xl mx-auto px-6 py-10 grid lg:grid-cols-[1fr,360px] gap-10">
      <div>
        <section className="border-b border-rule pb-6 mb-8">
          <div className="byline mb-2">Treasury · Mandate-enforced · Two-party authorised</div>
          <h2 className="masthead">Treasury</h2>
        </section>

        <form
          data-testid="propose-form"
          className="card p-6 mb-10 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!form.session_id) {
              setError("Pick a session first.");
              return;
            }
            propose.mutate({
              session_id: form.session_id,
              instrument: form.instrument,
              side: form.side,
              qty: form.qty,
              expected_price: form.expected_price || undefined,
            });
          }}
        >
          <h3 className="font-display text-2xl">Propose a trade</h3>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Session">
              <select
                value={form.session_id}
                onChange={(e) => setForm({ ...form, session_id: e.target.value })}
                className="field"
                data-testid="propose-session"
                required
              >
                <option value="">— select —</option>
                {sessions.data?.items.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title || s.id.slice(0, 8)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Instrument">
              <input
                value={form.instrument}
                onChange={(e) => setForm({ ...form, instrument: e.target.value })}
                className="field"
                data-testid="propose-instrument"
                list="instruments"
              />
              <datalist id="instruments">
                {mandate.data?.permitted_instruments.map((i) => (
                  <option key={i} value={i} />
                ))}
              </datalist>
            </Field>
            <Field label="Side">
              <select
                value={form.side}
                onChange={(e) => setForm({ ...form, side: e.target.value as "buy" | "sell" })}
                className="field"
                data-testid="propose-side"
              >
                <option value="buy">buy</option>
                <option value="sell">sell</option>
              </select>
            </Field>
            <Field label="Qty">
              <input
                type="number"
                step="0.0001"
                min="0.0001"
                value={form.qty}
                onChange={(e) => setForm({ ...form, qty: e.target.value })}
                className="field"
                data-testid="propose-qty"
              />
            </Field>
            <Field label="Expected price (optional)">
              <input
                value={form.expected_price}
                onChange={(e) => setForm({ ...form, expected_price: e.target.value })}
                className="field"
                data-testid="propose-price"
                placeholder="market"
              />
            </Field>
          </div>
          {error && (
            <p
              data-testid="propose-error"
              className="border border-accent bg-accent/10 p-3 font-ui text-sm text-accent"
            >
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={propose.isPending}
            className="btn-primary"
            data-testid="propose-submit"
          >
            {propose.isPending ? "Proposing…" : "Propose"}
          </button>
        </form>

        <section>
          <h3 className="byline mb-3">All proposals</h3>
          <ul className="divide-y divide-rule" data-testid="proposals-list">
            {proposals.data?.length === 0 && (
              <li className="font-display italic text-sub py-6">
                No proposals yet.
              </li>
            )}
            {proposals.data?.map((p) => (
              <ProposalRow key={p.id} p={p} currentUserId={user?.id ?? ""} />
            ))}
          </ul>
        </section>
      </div>

      <aside className="lg:sticky lg:top-6 self-start space-y-6">
        <section className="card p-5">
          <h3 className="byline mb-2">Active mandate</h3>
          {mandate.isLoading && <p className="font-ui text-sub">Loading…</p>}
          {mandate.isError && (
            <p className="font-display italic text-sub">No active mandate.</p>
          )}
          {mandate.data && (
            <dl className="text-sm font-ui space-y-2">
              <Row k="Version" v={`v${mandate.data.version}`} />
              <Row
                k="Daily loss limit"
                v={`${mandate.data.currency} ${mandate.data.daily_loss_limit}`}
              />
              <Row
                k="Single-instrument max"
                v={`${mandate.data.currency} ${mandate.data.single_instrument_max}`}
              />
              <Row
                k="Permitted instruments"
                v={mandate.data.permitted_instruments.join(", ")}
              />
              <Row
                k="Sides"
                v={mandate.data.permitted_sides.join(", ")}
              />
              <Row k="Authorisers" v={String(mandate.data.auth_user_ids.length)} />
            </dl>
          )}
        </section>
      </aside>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="byline mb-1 block">{label}</span>
      {children}
    </label>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between border-b border-rule py-1 gap-3">
      <dt className="text-sub uppercase tracking-wider text-xs">{k}</dt>
      <dd className="text-right font-display">{v}</dd>
    </div>
  );
}

function ProposalRow({
  p,
  currentUserId,
}: {
  p: TreasuryProposal;
  currentUserId: string;
}): JSX.Element {
  const qc = useQueryClient();
  const authMut = useMutation({
    mutationFn: () => authoriseProposal(p.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["proposals"] }),
  });
  const rejectMut = useMutation({
    mutationFn: (reason: string) => rejectProposal(p.id, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["proposals"] }),
  });

  const alreadyAuthorisedByMe = p.auth1_user_id === currentUserId;
  const canFirstAuth = p.state === "proposed";
  const canSecondAuth = p.state === "first_authorised" && !alreadyAuthorisedByMe;
  const canAuth = canFirstAuth || canSecondAuth;
  const blockedBySamePerson = p.state === "first_authorised" && alreadyAuthorisedByMe;

  return (
    <li className="py-5" data-testid="proposal-row" data-state={p.state}>
      <div className="flex items-baseline justify-between mb-2">
        <h4 className="font-display text-xl">
          {p.side.toUpperCase()} {p.qty} {p.instrument}
        </h4>
        <span className={`badge ${stateBadge(p.state)}`} data-testid="proposal-state">
          {p.state.replace("_", " ")}
        </span>
      </div>
      <p className="font-ui text-sm text-sub mb-3">
        Notional {p.notional_eur} EUR · proposed{" "}
        {new Date(p.proposed_at).toLocaleTimeString("en-GB")} · expires{" "}
        {new Date(p.expires_at).toLocaleTimeString("en-GB")}
      </p>
      {p.mandate_check && (
        <ul className="grid grid-cols-2 md:grid-cols-4 gap-1 font-ui text-xs text-sub mb-3">
          {(
            [
              ["instrument", p.mandate_check.permitted_instruments],
              ["side", p.mandate_check.permitted_sides],
              ["single-max", p.mandate_check.single_instrument_max],
              ["daily-loss", p.mandate_check.daily_loss_limit],
            ] as const
          ).map(([k, g]) => (
            <li
              key={k}
              className={`px-2 py-1 border ${
                g.pass ? "border-gold/40 text-gold" : "border-accent text-accent"
              }`}
            >
              {g.pass ? "✓" : "✗"} {k}
            </li>
          ))}
        </ul>
      )}
      {p.state === "executed" && (
        <p className="font-mono text-xs text-gold">
          ✓ Executed at {p.executed_price} · order {p.kraken_order_id}
        </p>
      )}
      {canAuth && (
        <div className="flex gap-3 mt-2">
          <button
            onClick={() => authMut.mutate()}
            disabled={authMut.isPending}
            className="btn-primary"
            data-testid="authorise-button"
          >
            {authMut.isPending
              ? "…"
              : canFirstAuth
                ? "Authorise (1 of 2)"
                : "Authorise (2 of 2)"}
          </button>
          <button
            onClick={() => rejectMut.mutate("Rejected by operator")}
            disabled={rejectMut.isPending}
            className="btn-secondary"
            data-testid="reject-button"
          >
            Reject
          </button>
        </div>
      )}
      {blockedBySamePerson && (
        <p className="font-ui text-xs text-accent" data-testid="two-party-warning">
          Two-party authorisation required — a different user must approve.
        </p>
      )}
    </li>
  );
}

function stateBadge(state: string): string {
  switch (state) {
    case "executed":
      return "bg-gold/15 text-gold";
    case "rejected":
    case "execution_failed":
      return "bg-accent/15 text-accent";
    case "first_authorised":
      return "bg-ink/10 text-ink";
    default:
      return "bg-muted text-sub";
  }
}
