import { useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Finding = {
  id: string;
  status: "open" | "resolved";
  explanation: string;
  expected: { amount_minor?: number } | null;
  actual: { amount_minor?: number } | null;
  resolved_at: string | null;
  resolved_by: string | null;
  adjustment_journal_id: string | null;
};

type Scenario = {
  tenant_id: string;
  access_token: string;
  accounts: { merchant: string; customer: string; provider_fee: string };
  transfer: { id: string; client_reference: string; amount_minor: number; journal_id: string };
  provider_event: { amount_minor: number; classification: string };
  transfer_replayed: boolean;
  provider_duplicate: boolean;
  statement: { id: string; content_hash: string; row_count: number };
  findings: Finding[];
};

type Entry = { account_id: string; amount_minor: number; position: number };
type Journal = { id: string; entries: Entry[] };
type Event = { occurred_at: string; kind: string; summary: string };
type Batch = { status: "imported" | "needs_review" | "ready_to_close" | "closed"; closed_at: string | null };
type Workspace = { scenario: Scenario; original: Journal; events: Event[]; batch: Batch; adjustment?: Journal };
type View = "Cases" | "Ledger" | "Activity";
type Filter = "All" | "Open" | "Resolved";

const API = import.meta.env.VITE_API_URL ?? "";
const formatMoney = new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN" });
const money = (minor: number) => formatMoney.format(minor / 100);
const brief = (value: string) => value.length > 22 ? value.slice(0, 8) + "…" + value.slice(-6) : value;

const icons = {
  logo: "M4 12l4-4 4 4 4-4 4 4-8 8-8-8Zm4-4 4-4 4 4",
  cases: "M4 5h16v14H4z M4 10h16m-11 0v9",
  ledger: "M5 4h14v16H5z m4 4h6m-6 4h6m-6 4h3",
  activity: "M3 12h4l2-5 4 10 3-5h5",
  code: "m8 7-5 5 5 5m8-10 5 5-5 5m-2-13-4 16",
  arrow: "M4 12h15m-6-6 6 6-6 6",
  plus: "M12 5v14M5 12h14",
  check: "m5 12 4 4L19 6",
  shield: "M12 3 5 6v5c0 4 3 8 7 10 4-2 7-6 7-10V6l-7-3Z m-3 9 2 2 4-4",
  warning: "M12 8v5m0 3h.01 M12 3l9 16H3l9-16Z",
  file: "M6 3h8l4 4v14H6z m8 0v5h4m-9 4h6m-6 4h6",
  external: "M13 5h6v6m0-6-8 8m6 0v6H5V7h6",
  close: "m6 6 12 12M18 6 6 18",
};

function Icon({ name, size = 18 }: { name: keyof typeof icons; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={icons[name]} /></svg>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(API + path, init);
  if (response.ok) return response.json();
  if (response.status === 401) throw new Error("This session expired. Run a new scenario to continue.");
  const failure = await response.json().catch(() => null);
  throw new Error(failure?.error?.message ?? "Proof could not complete this request. Try again.");
}

function tenantRequest<T>(scenario: Scenario, path: string, method = "GET"): Promise<T> {
  return request<T>(`/v1/tenants/${scenario.tenant_id}${path}`, {
    method, headers: { Authorization: `Bearer ${scenario.access_token}` },
  });
}

function Tag({ children, tone = "neutral" }: { children: string; tone?: string }) {
  return <span className={`tag ${tone}`}><i />{children}</span>;
}

function Orbit() {
  return <svg className="orbit" viewBox="0 0 460 170" aria-hidden="true">
    <defs>
      <pattern id="dot-grid" width="14" height="14" patternUnits="userSpaceOnUse">
        <circle cx="2" cy="2" r="0.9" fill="#e5dcff" opacity=".27" />
      </pattern>
      <linearGradient id="ribbon" x1="0" y1="0" x2="1" y2="1">
        <stop stopColor="#c9b9ff" /><stop offset="1" stopColor="#f1b9fd" />
      </linearGradient>
    </defs>
    <path d="M60 0h400v170H60z" fill="url(#dot-grid)" />
    <g transform="translate(290 86) rotate(-26)" fill="none">
      {[0, 1, 2, 3, 4, 5, 6].map(n =>
        <ellipse key={n} rx={112 + 12 * n} ry={19 + 7 * n} stroke="url(#ribbon)" opacity={.5 - n * .055} />)}
      <circle cx="115" cy="-15" r="4.5" fill="#f1dcff" /><circle cx="-147" cy="7" r="3" fill="#e7caff" />
    </g>
    <g transform="translate(271 57)">
      <rect width="60" height="60" rx="16" fill="#7658db" stroke="#bca8ff" />
      <path d="m15 30 9-9 6 6 6-6 9 9-15 15-15-15Zm9-9 6-6 6 6" fill="none"
        stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </g>
  </svg>;
}

function App() {
  const [view, setView] = useState<View>("Cases");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [filter, setFilter] = useState<Filter>("All");
  const [busy, setBusy] = useState<"start" | "resolve" | "close" | null>(null);
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [lastPosted, setLastPosted] = useState<number | null>(null);

  const scenario = workspace?.scenario;
  const finding = scenario?.findings[0];
  const resolved = finding?.status === "resolved";
  const expected = finding?.expected?.amount_minor ?? 2_500_000;
  const reported = finding?.actual?.amount_minor ?? 2_475_000;
  const difference = expected - reported;
  const selected = filter === "All" || (filter === "Resolved" ? resolved : !resolved);
  const status = resolved ? "Resolved" : "Needs review";
  const nav = { Cases: "cases", Ledger: "ledger", Activity: "activity" } as const;

  function navigate(next: View) {
    setView(next);
    setConfirm(false);
  }

  async function start() {
    setBusy("start");
    setError("");
    setConfirm(false);
    try {
      const next = await request<Scenario>("/v1/demo/scenarios/canonical", { method: "POST" });
      const [original, trace, batch] = await Promise.all([
        tenantRequest<Journal>(next, `/journals/${next.transfer.journal_id}`),
        tenantRequest<{ items: Event[] }>(next, `/operations/transfers/${next.transfer.id}/timeline`),
        tenantRequest<Batch>(next, `/settlements/batches/${next.statement.id}`),
      ]);
      setWorkspace({ scenario: next, original, events: trace.items, batch });
      setLastPosted(null);
      setFilter("All");
      navigate("Cases");
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function resolve() {
    if (!workspace || !scenario || !finding || resolved) return;
    setBusy("resolve");
    setError("");
    try {
      const result = await tenantRequest<Finding>(scenario, `/demo/findings/${finding.id}/adjust`, "POST");
      const next = { ...workspace, scenario: { ...scenario, findings: [result, ...scenario.findings.slice(1)] } };
      setWorkspace(next);
      setConfirm(false);
      if (result.adjustment_journal_id) {
        const [adjustment, balance, batch] = await Promise.all([
          tenantRequest<Journal>(scenario, `/journals/${result.adjustment_journal_id}`),
          tenantRequest<{ balance_minor: number }>(scenario, `/accounts/${scenario.accounts.customer}/balance`),
          tenantRequest<Batch>(scenario, `/settlements/batches/${scenario.statement.id}`),
        ]);
        setWorkspace({ ...next, adjustment, batch });
        setLastPosted(balance.balance_minor);
      }
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function closeBatch() {
    if (!workspace || !scenario) return;
    setBusy("close");
    setError("");
    try {
      const batch = await tenantRequest<Batch>(scenario, `/demo/settlements/${scenario.statement.id}/close`, "POST");
      setWorkspace({ ...workspace, batch });
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const displayId = finding ? `REC-${finding.id.slice(0, 6).toUpperCase()}` : "REC-DEMO";
  const names = scenario ? {
    [scenario.accounts.merchant]: "Merchant available",
    [scenario.accounts.customer]: "Customer payable",
    [scenario.accounts.provider_fee]: "Provider fee expense",
  } : {};
  const resolutionEvent: Event[] = finding?.resolved_at ? [{
    occurred_at: finding.resolved_at, kind: "resolution", summary: "Fee adjustment posted and finding resolved",
  }] : [];
  const closingEvent: Event[] = workspace?.batch.closed_at ? [{
    occurred_at: workspace.batch.closed_at, kind: "settlement", summary: "Settlement batch closed",
  }] : [];

  return (
    <div className="app">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="Proof home"><span className="brand-icon"><Icon name="logo" size={23} /></span>proof<span className="brand-dot">.</span></a>
        <div className="side-label">WORKSPACE</div>
        <nav aria-label="Workspace">
          {(Object.keys(nav) as View[]).map(item => (
            <button key={item} className={view === item ? "current" : ""} aria-current={view === item ? "page" : undefined}
              onClick={() => navigate(item)}><Icon name={nav[item]} />{item === "Cases" ? "Reconciliation" : item === "Ledger" ? "Ledger explorer" : "Event trail"}</button>
          ))}
        </nav>
        <div className="side-label secondary">RESOURCES</div>
        <nav aria-label="Resources">
          <a href={API + "/docs"} target="_blank" rel="noreferrer"><Icon name="code" />API reference<Icon name="external" size={13} /></a>
        </nav>
        <div className="side-footer"><span className="side-avatar"><Icon name="shield" size={19} /></span><div><strong>Proof Sandbox</strong><small>Fictional funds only</small></div></div>
      </aside>

      <div className="surface">
        <header className="topbar">
          <div className="crumb"><span>Workspace</span><span aria-hidden="true">/</span><strong>{view === "Cases" ? "Reconciliation" : view}</strong></div>
          <Tag tone="violet">Sandbox</Tag>
        </header>

        <main className="main">
          <div className="page-title">
            <div><p className="eyebrow">PAYMENT OPERATIONS</p><h1>{view === "Cases" ? "Reconciliation" : view === "Ledger" ? "Ledger explorer" : "Event trail"}</h1>
            <p>{view === "Cases" ? "Investigate settlement differences and close them with an audit trail." : view === "Ledger" ? "Inspect the original posting and its linked adjustment." : "Follow the transfer, provider evidence and resolution in order."}</p></div>
            <button className="button primary" onClick={start} disabled={!!busy}><Icon name="plus" size={17} />{busy === "start" ? "Starting…" : workspace ? "New scenario" : "Run demo"}</button>
          </div>

          {error && <div className="error" role="alert"><Icon name="warning" />{error}<button onClick={() => setError("")} aria-label="Dismiss error"><Icon name="close" /></button></div>}

          {view === "Cases" && <>
            <section className="banner" aria-label="Guided scenario">
              <div className="banner-content">
                <p className="banner-label"><Icon name="logo" size={15} /> GUIDED SCENARIO · 01</p>
                <h2>The ₦250 settlement gap</h2>
                <p>Trace a fictional payment from ledger to provider, then post the fee that closes the difference.</p>
              </div>
              <Orbit />
            </section>

            <section className="summary" aria-label={scenario ? "Scenario totals" : "Example totals"}>
              {[
                { name: "Ledger amount", value: expected, icon: "ledger", tone: "lavender" },
                { name: "Provider reported", value: reported, icon: "file", tone: "blue" },
                { name: resolved ? "Adjusted difference" : "Unreconciled difference", value: difference, icon: resolved ? "check" : "warning", tone: resolved ? "mint" : "amber" },
              ].map(metric => <article className="metric" key={metric.name}>
                <div className={`tile-icon ${metric.tone}`}><Icon name={metric.icon as keyof typeof icons} /></div>
                <div><span>{metric.name}</span><strong>{money(metric.value)}</strong></div>
              </article>)}
            </section>

            <div className="case-layout">
              <section className="panel queue" aria-labelledby="queue-title">
                <div className="panel-heading"><div><h2 id="queue-title">Case queue</h2><p>{scenario ? "Findings from the active scenario" : "Example data · run the demo to create a case"}</p></div><span className="count">1</span></div>
                <div className="filters" aria-label="Filter cases">
                  {(["All", "Open", "Resolved"] as Filter[]).map(item => <button key={item}
                    className={filter === item ? "selected" : ""} aria-pressed={filter === item}
                    onClick={() => setFilter(item)}>{item}</button>)}
                </div>
                <div className="table-scroll">
                  <table className="case-table"><thead><tr><th>Case</th><th>Difference</th><th>Status</th></tr></thead>
                    <tbody>{selected ? <tr className="active-row"><td><strong>Amount mismatch</strong><small>{displayId}</small></td><td className="numeric">{money(difference)}</td><td><Tag tone={resolved ? "green" : "gold"}>{scenario ? status : "Example"}</Tag></td></tr>
                      : <tr><td colSpan={3} className="empty-row">No {filter.toLowerCase()} cases.</td></tr>}</tbody>
                  </table>
                </div>
                <div className="queue-foot"><Icon name="shield" size={16} /> The original journal remains intact after an adjustment.</div>
              </section>

              <section className="panel detail" aria-labelledby="detail-title">
                <div className="panel-heading"><div><p className="eyebrow">{displayId}</p><h2 id="detail-title">Settlement difference</h2></div><Tag tone={resolved ? "green" : "gold"}>{scenario ? status : "Preview"}</Tag></div>
                <p className="detail-copy">{resolved ? "The fee is recorded in a separate, balanced journal." : "The provider statement reflects a fictional fee withheld from the original transfer."}</p>
                <dl className="compare"><div><dt>Ledger posted</dt><dd>{money(expected)}</dd></div><div><dt>Statement reported</dt><dd>{money(reported)}</dd></div>
                  <div className="variance"><dt>{resolved ? "Fee recorded" : "Difference"}</dt><dd>{money(difference)}</dd></div></dl>
                {!scenario && <button className="button secondary-button" disabled={!!busy} onClick={start}>Run this scenario<Icon name="arrow" size={16} /></button>}
                {scenario && !resolved && !confirm && <button className="button primary wide" disabled={!!busy} onClick={() => setConfirm(true)}>Review adjustment<Icon name="arrow" size={16} /></button>}
                {confirm && !resolved && <div className="review">
                  <h3>Proposed journal</h3><dl><div><dt>Customer payable</dt><dd>−{money(difference)}</dd></div><div><dt>Provider fee expense</dt><dd>+{money(difference)}</dd></div></dl>
                  <div className="review-actions"><button className="button secondary-button" disabled={!!busy} onClick={() => setConfirm(false)}>Cancel</button>
                    <button className="button primary" disabled={!!busy} onClick={resolve}>{busy === "resolve" ? "Posting…" : "Post adjustment"}</button></div>
                </div>}
                {resolved && <div className="success" role="status"><Icon name="check" /><div><strong>Adjustment posted</strong>{lastPosted !== null && <span>Customer payable now {money(lastPosted)}</span>}</div>
                  <button onClick={() => navigate("Ledger")}>View journal <Icon name="arrow" size={14} /></button></div>}
                {workspace?.batch.status === "ready_to_close" && <div className="batch-action">
                  <button className="button secondary-button" onClick={closeBatch} disabled={!!busy}>{busy === "close" ? "Closing…" : "Close settlement batch"}</button>
                </div>}
                {workspace?.batch.status === "closed" && <p className="batch-action" role="status"><Tag tone="green">Settlement closed</Tag></p>}
              </section>
            </div>
          </>}

          {view !== "Cases" && !workspace && <section className="panel empty"><Icon name={nav[view]} size={28} /><h2>No active scenario</h2><p>Run the guided demo to create records for this workspace.</p><button className="button primary" onClick={start} disabled={!!busy}>Run demo</button></section>}
          {view === "Ledger" && workspace && <div className="stack">
            {[workspace.original, workspace.adjustment].flatMap((journal, index) => journal ? [
              <section className="panel journal" key={journal.id}>
                <div className="panel-heading"><div><p className="eyebrow">{index === 0 ? "ORIGINAL POSTING" : "LINKED ADJUSTMENT"}</p>
                  <h2>{index === 0 ? "Merchant settlement" : "Provider settlement fee"}</h2><p className="identifier">{journal.id}</p></div><Tag tone="green">Posted</Tag></div>
                <div className="table-scroll"><table><thead><tr><th>Line</th><th>Account</th><th className="numeric">Signed amount</th></tr></thead>
                  <tbody>{journal.entries.map(entry => <tr key={entry.position}><td>{entry.position + 1}</td><td>{names[entry.account_id] ?? brief(entry.account_id)}</td>
                    <td className="numeric">{money(entry.amount_minor)}</td></tr>)}</tbody>
                  <tfoot><tr><th colSpan={2}>Net movement</th><td className="numeric">{money(journal.entries.reduce((total, entry) => total + entry.amount_minor, 0))}</td></tr></tfoot>
                </table></div>
              </section>,
            ] : [])}
          </div>}

          {view === "Activity" && workspace && scenario && <div className="activity-layout">
            <section className="panel">
              <div className="panel-heading"><div><h2>Transfer activity</h2><p>{scenario.transfer.client_reference}</p></div><Tag tone="violet">Fictional</Tag></div>
              <ol className="event-list">{[...workspace.events, ...resolutionEvent, ...closingEvent].map((item, index) =>
                <li key={index}><span className="event-icon"><Icon name={item.kind === "resolution" ? "check" : "activity"} size={16} /></span>
                  <div><small>{item.kind.replaceAll("_", " ")}</small><strong>{item.summary}</strong></div>
                  <time dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleTimeString([], { timeStyle: "medium" })}</time></li>)}</ol>
            </section>
            <section className="panel trace">
              <div className="panel-heading"><div><h2>Evidence references</h2><p>From the active scenario</p></div></div>
              <dl className="refs">
                <div><dt>Transfer</dt><dd>{scenario.transfer.id}</dd></div>
                <div><dt>Statement SHA-256</dt><dd>{scenario.statement.content_hash}</dd></div>
                <div><dt>Provider classification</dt><dd>{scenario.provider_event.classification}</dd></div>
                <div><dt>Transfer retry</dt><dd>{scenario.transfer_replayed ? "Original transfer returned" : "No replay recorded"}</dd></div>
                <div><dt>Duplicate callback</dt><dd>{scenario.provider_duplicate ? "Original evidence returned" : "No duplicate recorded"}</dd></div>
                {finding?.resolved_by && <div><dt>Audited actor</dt><dd>{finding.resolved_by}</dd></div>}
              </dl>
            </section>
          </div>}
          <footer>Proof <span>·</span> Every cent accounted for <span>·</span> Simulated funds</footer>
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
