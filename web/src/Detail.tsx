import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import { Chip, ErrorPanel, StatePanel, money, number, Reasons } from "./ui";
import { categoryNames, groupName, label, type Direction } from "./research";
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
                    onChange={(e) => setDirection(e.target.value as Direction)}
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
                <small>Stored decision</small>
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
                      <b>{review.strength_summary}</b>
                    </p>
                    <p>
                      Trade-universe membership:{" "}
                      {review.trade_universe_eligible
                        ? "Eligible"
                        : "Not eligible"}{" "}
                      ·{" "}
                      {o.group.sub_industry
                        ? groupName(o.group.sub_industry.group_id)
                        : "Sub-industry unassigned"}
                    </p>
                    <p>
                      <b>Active setup: </b>
                      {review.active_setups.length
                        ? review.active_setups
                            .map(
                              (s) => label(s.family) + " · " + label(s.status),
                            )
                            .join("; ")
                        : "None in this direction"}
                      .
                    </p>
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
                    {o.decision.setups
                      .filter(
                        (s) =>
                          !s.active || s.direction !== o.decision.direction,
                      )
                      .map((s) => (
                        <p key={s.setup_id}>
                          {label(s.family)} · {s.direction} ·{" "}
                          <Chip value={s.status} />
                        </p>
                      ))}
                  </details>
                </>
              )}
              {tab === "Decision evidence" && (
                <>
                  <h3>Decision evidence</h3>
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
