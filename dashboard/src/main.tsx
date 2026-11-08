import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Finding = {
  id: string;
  kind: string;
  status: string;
  expected: Record<string, unknown> | null;
  actual: Record<string, unknown> | null;
  adjustment_journal_id: string | null;
};

type Scenario = {
  tenant_id: string;
  tenant_name: string;
  fictional: boolean;
  accounts: { system: string; merchant: string; customer: string; provider_fee: string };
  transfer: {
    id: string;
    client_reference: string;
    amount_minor: number;
    currency: string;
    status: string;
    journal_id: string;
  };
  provider_event: {
    id: string;
    amount_minor: number;
    classification: string;
    provider_status: string;
  };
  statement: { id: string; content_hash: string; row_count: number };
  reconciliation_run_id: string;
  findings: Finding[];
};

type TimelineItem = {
  occurred_at: string;
  kind: string;
  summary: string;
  data: Record<string, unknown>;
};

const API = import.meta.env.VITE_API_URL ?? "";

function money(minor: number) {
  return new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN" }).format(minor / 100);
}

function short(value?: string | null) {
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
}

function Icon({ name }: { name: "pulse" | "ledger" | "route" | "shield" }) {
  const paths = {
    pulse: <path d="M3 12h4l2-7 4 14 2-7h6" />,
    ledger: <><path d="M5 3h14v18H5z"/><path d="M8 8h8M8 12h8M8 16h5"/></>,
    route: <><circle cx="5" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="M7 6h5a4 4 0 0 1 4 4v0a4 4 0 0 1-4 4H9a4 4 0 0 0-4 4v0"/></>,
    shield: <><path d="M12 3 5 6v5c0 5 3 8 7 10 4-2 7-5 7-10V6z"/><path d="m9 12 2 2 4-4"/></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>;
}

function App() {
  const [scenario, setScenario] = useState<Scenario | null>(() => {
    const saved = localStorage.getItem("proof-scenario");
    return saved ? JSON.parse(saved) : null;
  });
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const finding = scenario?.findings[0] ?? null;
  const resolved = finding?.status === "resolved";
  const discrepancy = scenario
    ? Number(finding?.expected?.amount_minor ?? scenario.transfer.amount_minor) -
      Number(finding?.actual?.amount_minor ?? scenario.provider_event.amount_minor)
    : 25_000;

  async function refreshTimeline(next: Scenario) {
    const response = await fetch(
      `${API}/v1/tenants/${next.tenant_id}/operations/transfers/${next.transfer.id}/timeline`,
      { headers: { "X-Tenant-ID": next.tenant_id } },
    );
    if (response.ok) setTimeline((await response.json()).items);
  }

  useEffect(() => {
    if (scenario) refreshTimeline(scenario).catch(() => undefined);
  }, []);

  async function runIncident() {
    setBusy(true); setError("");
    try {
      const response = await fetch(`${API}/v1/demo/scenarios/canonical`, { method: "POST" });
      if (!response.ok) throw new Error("Could not create the guided incident.");
      const next: Scenario = await response.json();
      setScenario(next);
      localStorage.setItem("proof-scenario", JSON.stringify(next));
      await refreshTimeline(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unexpected failure");
    } finally { setBusy(false); }
  }

  async function resolveFinding() {
    if (!scenario || !finding) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(
        `${API}/v1/tenants/${scenario.tenant_id}/reconciliation/findings/${finding.id}/resolve`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Tenant-ID": scenario.tenant_id,
            "X-Operator-ID": "portfolio-operator@proof.demo",
          },
          body: JSON.stringify({
            resolution: "adjusted",
            reason: "Recognize the fictional provider settlement fee.",
            adjustment_description: "Provider fee reconciliation adjustment",
            adjustment_entries: [
              { account_id: scenario.accounts.customer, amount_minor: -discrepancy },
              { account_id: scenario.accounts.provider_fee, amount_minor: discrepancy },
            ],
          }),
        },
      );
      if (!response.ok) throw new Error("The controlled adjustment could not be posted.");
      const updated: Finding = await response.json();
      const next = { ...scenario, findings: [updated, ...scenario.findings.slice(1)] };
      setScenario(next); localStorage.setItem("proof-scenario", JSON.stringify(next));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unexpected failure");
    } finally { setBusy(false); }
  }

  const steps = useMemo(() => timeline.length ? timeline : [
    { occurred_at: "", kind: "transfer", summary: "Transfer command accepted", data: {} },
    { occurred_at: "", kind: "journal", summary: "Balanced journal posted", data: {} },
    { occurred_at: "", kind: "provider_evidence", summary: "Provider mismatch detected", data: {} },
  ], [timeline]);

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand-mark">P<span>.</span></div>
        <nav aria-label="Primary">
          <button className="nav-active" aria-label="Operations"><Icon name="pulse" /></button>
          <button aria-label="Ledger"><Icon name="ledger" /></button>
          <button aria-label="Flows"><Icon name="route" /></button>
          <button aria-label="Controls"><Icon name="shield" /></button>
        </nav>
        <div className="rail-status"><i />API</div>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <div className="eyebrow">PAYMENT OPERATIONS / <b>FICTIONAL SANDBOX</b></div>
            <h1>Proof<span>.</span></h1>
          </div>
          <div className="top-actions">
            <div className="environment"><i /> SYSTEM HEALTHY</div>
            <button className="run-button" onClick={runIncident} disabled={busy}>
              {busy ? "Running proof…" : scenario ? "Run fresh incident" : "Run guided incident"}
            </button>
          </div>
        </header>

        {error && <div className="error-banner">{error}</div>}

        <section className="intro">
          <div>
            <p className="section-kicker">LIVE CONTROL SURFACE</p>
            <h2>Every cent has<br />a reason.</h2>
          </div>
          <p className="intro-copy">Trace a transfer from command to journal, compare it with provider evidence, and resolve the mismatch without rewriting history.</p>
        </section>

        <section className="metrics">
          <article><span>LEDGER INTEGRITY</span><strong className="good">BALANCED</strong><small>Σ entries = 0</small></article>
          <article><span>TRANSFER</span><strong>{scenario ? money(scenario.transfer.amount_minor) : "₦25,000.00"}</strong><small>{scenario ? short(scenario.transfer.id) : "awaiting incident"}</small></article>
          <article><span>RECONCILIATION</span><strong className={resolved ? "good" : "alert"}>{resolved ? "RESOLVED" : "1 OPEN"}</strong><small>{money(discrepancy)} difference</small></article>
          <article><span>EVIDENCE</span><strong>{scenario ? "3 SOURCES" : "READY"}</strong><small>ledger · provider · statement</small></article>
        </section>

        <section className="workspace">
          <article className="panel flow-panel">
            <div className="panel-head"><span>01 / MONEY FLOW</span><em>IMMUTABLE</em></div>
            <div className="flow-stage">
              <div className="node source"><small>SOURCE</small><b>Merchant</b><span>{scenario ? money(scenario.transfer.amount_minor) : "₦25,000"}</span></div>
              <div className="flow-line"><span>−</span><i /><b>{scenario ? short(scenario.transfer.journal_id) : "journal proof"}</b><i /><span>+</span></div>
              <div className="node destination"><small>DESTINATION</small><b>Customer payable</b><span>{scenario ? money(scenario.transfer.amount_minor) : "₦25,000"}</span></div>
            </div>
            <div className="equation"><b>DEBITS</b><span>{money(scenario?.transfer.amount_minor ?? 2_500_000)}</span><i>=</i><b>CREDITS</b><span>{money(scenario?.transfer.amount_minor ?? 2_500_000)}</span></div>
          </article>

          <article className="panel incident-panel">
            <div className="panel-head"><span>02 / RECONCILIATION</span><em className={resolved ? "success-pill" : "danger-pill"}>{resolved ? "CLOSED" : "ACTION REQUIRED"}</em></div>
            <div className="incident-title"><div className="warning">!</div><div><small>AMOUNT MISMATCH</small><h3>{money(discrepancy)}</h3></div></div>
            <div className="compare"><div><span>INTERNAL LEDGER</span><b>{scenario ? money(scenario.transfer.amount_minor) : "₦25,000.00"}</b></div><div><span>PROVIDER STATEMENT</span><b>{scenario ? money(scenario.provider_event.amount_minor) : "₦24,750.00"}</b></div></div>
            <p>The provider retained a fictional settlement fee. Proof preserves both records and requires an explicit adjustment.</p>
            <button className="resolve-button" disabled={!scenario || resolved || busy} onClick={resolveFinding}>{resolved ? "Adjustment posted ✓" : "Post controlled adjustment"}</button>
          </article>

          <article className="panel evidence-panel">
            <div className="panel-head"><span>03 / PROOF</span><em>APPEND-ONLY</em></div>
            <div className="stamp"><div>VERIFIED</div><span>DOUBLE ENTRY</span></div>
            <dl>
              <div><dt>Transaction</dt><dd>{short(scenario?.transfer.id)}</dd></div>
              <div><dt>Journal</dt><dd>{short(scenario?.transfer.journal_id)}</dd></div>
              <div><dt>Statement hash</dt><dd>{short(scenario?.statement.content_hash)}</dd></div>
              <div><dt>Provider class</dt><dd>{scenario?.provider_event.classification ?? "conflict"}</dd></div>
            </dl>
          </article>
        </section>

        <section className="timeline-section">
          <div className="timeline-heading"><div><p className="section-kicker">CAUSAL TRACE</p><h3>What happened, in order.</h3></div><span>{scenario?.tenant_name ?? "No scenario loaded"}</span></div>
          <div className="timeline">
            {steps.map((item, index) => <div className="timeline-item" key={`${item.kind}-${index}`}><span className="step">{String(index + 1).padStart(2, "0")}</span><i /><div><small>{item.kind.replaceAll("_", " ")}</small><b>{item.summary}</b><em>{item.occurred_at ? new Date(item.occurred_at).toLocaleTimeString() : "deterministic demo"}</em></div></div>)}
          </div>
        </section>

        <footer><span>PROOF / EVERY CENT ACCOUNTED FOR</span><span>SIMULATED FUNDS · NO REAL MONEY</span></footer>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
