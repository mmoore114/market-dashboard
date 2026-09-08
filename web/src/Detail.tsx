import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import { Chip, ErrorPanel, StatePanel, money, number, Reasons } from "./ui";
import { categoryNames, label, type Direction } from "./research";
const tabs = [
  "Overview",
  "Setups",
  "Decision evidence",
  "Data details",
] as const;
export function Detail({
  symbol,
  initialDirection = "LONG",
  onClose,
  onSize,
}: {
  symbol: string;
  initialDirection?: Direction;
  onClose: () => void;
  onSize: (symbol: string, direction: Direction) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState<(typeof tabs)[number]>("Overview");
  const [copied, setCopied] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const [direction, setDirection] = useState<Direction>(initialDirection);
  const query = useQuery({
    queryKey: ["symbol", symbol],
    queryFn: () =>
      get<Schemas["SymbolDetailV2"]>(
        "/symbols/" + encodeURIComponent(symbol),
        undefined,
        "v2",
      ),
  });
  useEffect(() => {
    const focused = document.activeElement as HTMLElement | null;
    const modal = dialog.current;
    const scroll = window.scrollY;
    modal?.showModal();
    return () => {
      modal?.close();
      focused?.focus({ preventScroll: true });
      window.scrollTo(0, scroll);
    };
  }, []);
  const record =
    query.data?.records.find(
      (r) => r.output.decision.direction === direction,
    ) ?? query.data?.records[0];
  const o = record?.output;
  const review = record?.review;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(symbol);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <dialog
      ref={dialog}
      className="detail-drawer research-detail"
      aria-labelledby="detail-title"
      onCancel={onClose}
    >
      <header className="drawer-header">
        <div>
          <h2 id="detail-title">
            {symbol}{" "}
            <span className="company-name">{record?.display_name}</span>
          </h2>
          <span className="muted">
            Price as of {query.data?.meta.as_of_session ?? "…"} ·{" "}
            {query.data?.meta.mode_label}
          </span>
        </div>
        <button aria-label="Close symbol detail" onClick={onClose}>
          Close ×
        </button>
      </header>
      {query.isPending ? (
        <StatePanel title="Loading symbol evidence">
          Reading bounded local evidence…
        </StatePanel>
      ) : query.error ? (
        <ErrorPanel error={query.error} />
      ) : (
        record &&
        query.data &&
        o &&
        review && (
          <>
            <div className="detail-actions">
              <button onClick={() => void copy()}>
                {copied ? "Symbol copied" : "Copy symbol / Deepvue"}
              </button>
              <button
                className="primary-button"
                onClick={() => onSize(symbol, o.decision.direction)}
              >
                Size this idea →
              </button>
              {query.data.records.length > 1 && (
                <label>
                  Evidence direction
                  <select
                    value={direction}
                    onChange={(e) => {
                      setDirection(e.target.value as Direction);
                      setHistoryPage(1);
                    }}
                  >
                    {query.data.records.map((r) => (
                      <option key={r.output.decision.direction}>
                        {r.output.decision.direction}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <small>Open your Deepvue chart workspace manually.</small>
            </div>
            <div className="detail-summary">
              <div>
                <small>
                  Stored decision ·{" "}
                  {review.policy_version === "decision-risk-v2"
                    ? "industry V2"
                    : "sub-industry V1"}
                </small>
                <Chip value={o.decision.state} />
              </div>
              <div>
                <small>Close</small>
                <b>{money(o.inputs.features.close)}</b>
              </div>
              <div>
                <small>Structure</small>
                <Chip value={o.inputs.structure?.state} />
              </div>
              <div>
                <small>RS composite / rotation</small>
                <b>
                  {number(o.strength.RS_comp)} /{" "}
                  {number(o.strength.RS_rotation)}
                </b>
              </div>
            </div>
            <div
              className="detail-tabs"
              role="tablist"
              aria-label="Stock detail sections"
            >
              {tabs.map((t) => (
                <button
                  key={t}
                  role="tab"
                  aria-selected={tab === t}
                  onClick={() => setTab(t)}
                >
                  {t}
                </button>
              ))}
            </div>
            <section role="tabpanel" aria-label={tab}>
              {tab === "Overview" && (
                <>
                  <div className="overview-context">
                    <p>
                      <b>Current setup: </b>
                      {review.current_setup.setup
                        ? label(review.current_setup.setup.family) +
                          " · " +
                          label(review.current_setup.setup.status)
                        : review.current_setup.state === "NONE"
                          ? "No current setup"
                          : "Evaluation unavailable"}
                    </p>
                    <p>
                      <b>{review.strength_summary}</b>
                    </p>
                    <p>
                      Trade-universe membership:{" "}
                      {review.trade_universe_eligible
                        ? "Eligible"
                        : "Not eligible"}{" "}
                      ·{" "}
                      {review.industry
                        ? `${review.industry.name} · rank ${review.industry.rank ?? "unavailable"} / ${review.industry.eligible_count}`
                        : "Industry unavailable"}
                    </p>
                    {review.blockers.length ? (
                      <button onClick={() => setTab("Decision evidence")}>
                        Next: review primary blocker →
                      </button>
                    ) : (
                      <button onClick={() => void copy()}>
                        Next: copy symbol for Deepvue review →
                      </button>
                    )}
                  </div>
                  <h3>Primary blockers</h3>
                  <ul className="blocker-list">
                    {review.blockers.slice(0, 3).map((b) => (
                      <li key={b.title}>
                        <span
                          className={
                            "blocker-category " + b.category.toLowerCase()
                          }
                        >
                          {categoryNames[b.category]}
                        </span>
                        <div>
                          <b>{b.title}</b>
                          <p>{b.detail}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                  {review.blockers.length > 3 && (
                    <button onClick={() => setTab("Decision evidence")}>
                      Review all {review.blockers.length} blockers →
                    </button>
                  )}
                  {review.blockers.length === 0 && (
                    <p>
                      All stored decision gates passed. ACT requests
                      discretionary chart review, not an order.
                    </p>
                  )}
                </>
              )}
              {tab === "Setups" && (
                <>
                  <p>
                    One evaluated setup is selected for display. Decision
                    eligibility considers every instance independently; the
                    displayed setup does not override stored vetoes.
                  </p>
                  <h3>Active setups · {o.decision.direction}</h3>
                  {review.active_setups.length === 0 && (
                    <p>No active setup in this direction.</p>
                  )}
                  {review.active_setups.map((s) => (
                    <article className="setup-card" key={s.setup_id}>
                      <h3>
                        {label(s.family)} <Chip value={s.status} />
                      </h3>
                      <p>{s.qualification}</p>
                      <div className="geometry">
                        <span>Frozen reference {money(s.trigger)}</span>
                        <span>
                          Lifecycle invalidation {money(s.invalidation)}
                        </span>
                      </div>
                      <p className="muted">
                        Lifecycle invalidation is not your proposed trade stop.
                        References come from canonical setup geometry.
                      </p>
                      {(s.local_errors.length > 0 ||
                        s.replay_required ||
                        !s.evaluated) && (
                        <p className="inline-warning">
                          {s.local_errors.map(label).join("; ")}{" "}
                          {s.replay_required
                            ? "Corrected-data replay required."
                            : ""}{" "}
                          {!s.evaluated
                            ? "Not evaluated for this session."
                            : ""}
                        </p>
                      )}
                      {s.unrelated_errors.length > 0 && (
                        <details>
                          <summary>
                            Other detection errors (separate scope)
                          </summary>
                          {s.unrelated_errors.map(label).join("; ")}
                        </details>
                      )}
                    </article>
                  ))}
                  {review.notes.map((n) => (
                    <p className="inline-warning" key={n}>
                      {n}
                    </p>
                  ))}
                  <details>
                    <summary>
                      Terminal history ({review.historical_count}) & opposite
                      direction ({review.opposite_direction_count})
                    </summary>
                    <p>
                      Available retained instances, newest status change first.
                      Terminal instances are retained for 20 trading sessions
                      (roughly one month); active instances may have older
                      births. This is available lifecycle evidence, not a
                      complete 60-day daily archive. Full local evidence remains
                      in Data details.
                    </p>
                    {(o.inputs.setups?.setups ?? [])
                      .filter(
                        (s) =>
                          !["FORMING", "NEAR_TRIGGER", "TRIGGERED"].includes(
                            s.instance.status,
                          ) || s.instance.direction !== o.decision.direction,
                      )
                      .sort(
                        (a, b) =>
                          b.instance.status_changed_at.localeCompare(
                            a.instance.status_changed_at,
                          ) ||
                          a.instance.setup_id.localeCompare(
                            b.instance.setup_id,
                          ),
                      )
                      .slice((historyPage - 1) * 20, historyPage * 20)
                      .map((s) => (
                        <p key={s.instance.setup_id}>
                          {label(s.instance.family)} · {s.instance.direction} ·{" "}
                          <Chip value={s.instance.status} /> · born{" "}
                          {s.instance.detected_at} · changed{" "}
                          {s.instance.status_changed_at}
                        </p>
                      ))}
                    <button
                      disabled={historyPage === 1}
                      onClick={() => setHistoryPage(historyPage - 1)}
                    >
                      Previous history
                    </button>
                    <span> Page {historyPage} </span>
                    <button
                      disabled={
                        historyPage * 20 >=
                        review.historical_count +
                          review.opposite_direction_count
                      }
                      onClick={() => setHistoryPage(historyPage + 1)}
                    >
                      Next history
                    </button>
                  </details>
                </>
              )}
              {tab === "Decision evidence" && (
                <>
                  <h3>Decision evidence</h3>
                  <p>
                    Stored policy: {review.policy_version}.{" "}
                    {review.policy_version === "decision-risk-v1"
                      ? "This historical policy used sub-industry as a gate; displaying industry leadership does not recalculate this decision."
                      : "Industry leadership is the primary group gate. Sub-industry and themes are context."}
                  </p>
                  <p>
                    These explanations describe the retained {o.decision.state}{" "}
                    decision. Optional alternatives and unentered proposals are
                    not stock-data failures.
                  </p>
                  <ul className="blocker-list">
                    {review.blockers.map((b) => (
                      <li key={b.title}>
                        <span
                          className={
                            "blocker-category " + b.category.toLowerCase()
                          }
                        >
                          {categoryNames[b.category]}
                        </span>
                        <div>
                          <b>{b.title}</b>
                          <p>{b.detail}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                  <details>
                    <summary>
                      Industry, broader groups, sub-industry paths & themes
                    </summary>
                    {review.memberships.map((g) => (
                      <p key={g.level + g.group_id}>
                        <b>
                          {label(g.level)} · {g.name}
                        </b>{" "}
                        · rank {g.rank ?? "unavailable"} / {g.eligible_count} ·
                        coverage {g.valid_members} / {g.total_members}
                        <br />
                        {g.parent}
                      </p>
                    ))}
                  </details>
                  <details>
                    <summary>Strength alternatives</summary>
                    <p>{review.strength_summary}</p>
                    <p>
                      Established: {String(o.strength.established_strength)};
                      rotation: {String(o.strength.new_rotation)}. Either branch
                      can independently pass.
                    </p>
                    <p>
                      Rotation spread: {number(o.strength.rotation_delta)}{" "}
                      points (rotation RS − composite RS), not historical
                      change.
                    </p>
                  </details>
                  <details>
                    <summary>Complete original decision checklist</summary>
                    {o.decision.gates.map((g) => (
                      <section key={g.name}>
                        <h4>
                          {g.rung} / {label(g.name)} · stored{" "}
                          {g.passed ? "pass" : "fail"}
                        </h4>
                        <Reasons reasons={g.reasons} />
                      </section>
                    ))}
                  </details>
                </>
              )}
              {tab === "Data details" && (
                <>
                  <p>
                    Frozen snapshot evidence; interpretation version{" "}
                    {review.schema_version}. Stored decisions and original
                    hashes are not rewritten by this view.
                  </p>
                  <dl>
                    <dt>Snapshot fingerprint</dt>
                    <dd>
                      <code>{query.data.meta.fingerprint}</code>
                    </dd>
                    <dt>Complete output reference</dt>
                    <dd>
                      <code>
                        {record.output_ref.index} · {record.output_ref.id}
                      </code>
                    </dd>
                    <dt>Shared Leadership reference</dt>
                    <dd>
                      <code>{o.inputs.leadership_ref?.id}</code>
                    </dd>
                    <dt>Shared Regime reference</dt>
                    <dd>
                      <code>{o.inputs.regime_ref?.id}</code>
                    </dd>
                  </dl>
                  <p>
                    Complete shared evidence remains available through the
                    fingerprint-bound V2 evidence API; this browser does not
                    download the full graph.
                  </p>
                  <details>
                    <summary>Original local evidence JSON</summary>
                    <pre>{JSON.stringify(o, null, 2)}</pre>
                  </details>
                </>
              )}
            </section>
          </>
        )
      )}
    </dialog>
  );
}
