import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import {
  Chip,
  ErrorPanel,
  Metric,
  Reasons,
  StatePanel,
  money,
  number,
} from "./ui";
import { SizingResult } from "./Sizer";

export function Detail({
  symbol,
  onClose,
  onSize,
}: {
  symbol: string;
  onClose: () => void;
  onSize: (symbol: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [copied, setCopied] = useState(false);
  const query = useQuery({
    queryKey: ["symbol", symbol],
    queryFn: () =>
      get<Schemas["SymbolDetailV2"]>(
        `/symbols/${encodeURIComponent(symbol)}`,
        undefined,
        "v2",
      ),
  });
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const modal = dialog.current;
    modal?.showModal();
    return () => {
      modal?.close();
      previouslyFocused?.focus();
    };
  }, []);
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
      className="detail-drawer"
      aria-labelledby="detail-title"
      onCancel={onClose}
    >
      <header className="drawer-header">
        <div>
          <span className="eyebrow">SYMBOL EVIDENCE</span>
          <h2 id="detail-title">{symbol}</h2>
        </div>
        <button aria-label="Close symbol detail" onClick={onClose}>
          Close ×
        </button>
      </header>
      {query.isPending ? (
        <StatePanel title="Loading symbol evidence">
          Reading the complete checklist…
        </StatePanel>
      ) : query.error ? (
        <ErrorPanel error={query.error} retry={() => void query.refetch()} />
      ) : (
        <>
          <div className="drawer-context">
            {query.data.meta.mode_label} · {query.data.meta.as_of_session} →{" "}
            {query.data.meta.action_session}
          </div>
          <div className="manual-handoff">
            <div>
              <b>Review chart in Deepvue</b>
              <p>
                Copy this exact symbol and open your chart workspace manually.
              </p>
            </div>
            <button onClick={() => void copy()}>
              {copied ? "Symbol copied" : "Copy symbol"}
            </button>
            <span className="copy-symbol">{symbol}</span>
          </div>
          {query.data.records.map((record) => {
            const o = record.output;
            return (
              <article key={o.decision.direction}>
                <div className="detail-heading">
                  <h3>
                    {record.display_name} · {o.decision.direction}
                  </h3>
                  <Chip value={o.decision.state} />
                </div>
                <div className="metric-grid">
                  <Metric
                    label="Close"
                    value={money(o.inputs.features.close)}
                  />
                  <Metric label="Volume" value={number(record.volume, 0)} />
                  <Metric
                    label="SMA50"
                    value={money(o.inputs.features.sma50)}
                  />
                  <Metric
                    label="Wilder ATR14"
                    value={number(o.inputs.features.wilder_atr14, 2)}
                  />
                </div>
                {record.volume_reason && (
                  <p className="muted">{record.volume_reason}</p>
                )}
                <section className="detail-section">
                  <h3>Decision checklist</h3>
                  <ul className="checklist">
                    {o.decision.gates.map((g) => (
                      <li key={g.name}>
                        <div>
                          <b>
                            {g.rung} / {g.name.replaceAll("_", " ")}
                          </b>
                          <Chip value={g.passed ? "PASS" : "FAIL"} />
                        </div>
                        <Reasons reasons={g.reasons} />
                      </li>
                    ))}
                  </ul>
                </section>
                <section className="detail-section">
                  <h3>Structure</h3>
                  <Chip value={o.inputs.structure?.state} />
                  <p>
                    {o.inputs.structure?.reason_codes.join(" · ") ??
                      "Structure evidence unavailable"}
                  </p>
                </section>
                <section className="detail-section">
                  <h3>Strength & rotation</h3>
                  <div className="metric-grid">
                    <Metric
                      label="RS composite"
                      value={number(o.strength.RS_comp)}
                    />
                    <Metric
                      label="RS rotation"
                      value={number(o.strength.RS_rotation)}
                    />
                    <Metric
                      label="Rotation delta"
                      value={number(o.strength.rotation_delta)}
                    />
                  </div>
                  <p>
                    Established:{" "}
                    {o.strength.established_strength == null
                      ? "Unknown"
                      : o.strength.established_strength
                        ? "Pass"
                        : "Fail"}{" "}
                    · New rotation:{" "}
                    {o.strength.new_rotation == null
                      ? "Unknown"
                      : o.strength.new_rotation
                        ? "Pass"
                        : "Fail"}
                  </p>
                  <Reasons reasons={o.strength.reasons} />
                </section>
                <section className="detail-section">
                  <h3>Sub-industry</h3>
                  <p>
                    {o.group.sub_industry?.group_id ?? "Unknown membership"} ·
                    rank {number(o.group.sub_industry?.leadership_rank)}
                  </p>
                  <Chip value={o.group.status} />
                  <p>
                    Rotation rank {number(o.group.group_rotation_rank)} · rank
                    advantage {number(o.group.rotation_rank_advantage)}
                  </p>
                  <p>
                    Themes (nonvoting):{" "}
                    {o.group.themes.map((g) => g.group_id).join(", ") ||
                      "None supplied"}
                  </p>
                  <Reasons reasons={o.group.reasons} />
                </section>
                <section className="detail-section">
                  <h3>Regime</h3>
                  <Chip value={o.regime.state} />
                  <p>
                    Eligible from{" "}
                    {o.regime.eligible_from_session ?? "Unavailable"}
                  </p>
                  <Reasons reasons={o.regime.reasons} />
                </section>
                <section className="detail-section">
                  <h3>Extension</h3>
                  <p>
                    {number(o.extension.signed_extension_sma50_atr, 2)} ATR ·{" "}
                    {o.extension.inputs.direction}
                  </p>
                  <Chip value={o.extension.state} />
                  <Reasons reasons={o.extension.reasons} />
                </section>
                <section className="detail-section">
                  <h3>Earnings</h3>
                  <Chip value={o.earnings.eligibility} />
                  <p>
                    Coverage through{" "}
                    {o.earnings.coverage?.covered_through ?? "Unknown"} ·
                    required through{" "}
                    {o.earnings.coverage_required_through ?? "Unknown"}
                  </p>
                  <Reasons reasons={o.earnings.reasons} />
                  {o.earnings.events.map((e, i) => (
                    <div className="event-record" key={i}>
                      <b>
                        {e.inputs.event_type} ·{" "}
                        {e.inputs.scheduled_session ?? "Unknown date"}
                      </b>
                      <p>
                        {e.inputs.timing} · {e.inputs.confidence} ·{" "}
                        {e.inputs.status} · distance{" "}
                        {number(e.sessions_until_event, 0)}
                      </p>
                      <Reasons reasons={e.reasons} />
                    </div>
                  ))}
                </section>
                <section className="detail-section">
                  <h3>
                    All setup instances{" "}
                    <span className="count">{o.decision.setups.length}</span>
                  </h3>
                  {o.decision.setups.length === 0 ? (
                    <p className="muted">No setup instances supplied.</p>
                  ) : (
                    o.decision.setups.map((s) => (
                      <div className="setup-record" key={s.setup_id}>
                        <div>
                          <b>
                            {s.family.replaceAll("_", " ")} · {s.direction}
                          </b>
                          <Chip value={s.status} />
                        </div>
                        <code>{s.setup_id}</code>
                        <p>
                          Evaluated: {String(s.evaluated)} · replay required:{" "}
                          {String(s.replay_required)} · ACT eligible:{" "}
                          {String(s.act_eligible)}
                        </p>
                        <p>
                          Lifecycle invalidation: {money(s.invalidation_level)}{" "}
                          · separate from the trade stop
                        </p>
                        <Reasons reasons={s.reasons} />
                      </div>
                    ))
                  )}
                </section>
                <section className="detail-section">
                  <h3>Current sizing evidence</h3>
                  <button
                    className="primary-button"
                    onClick={() => onSize(symbol)}
                  >
                    Open Sizer what-if →
                  </button>
                  <SizingResult result={o.sizing} />
                </section>
              </article>
            );
          })}
        </>
      )}
    </dialog>
  );
}
