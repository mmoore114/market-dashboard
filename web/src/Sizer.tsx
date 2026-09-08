import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import {
  ErrorPanel,
  Metric,
  PageTitle,
  Reasons,
  money,
  number,
  StatePanel,
} from "./ui";
import type { Direction } from "./research";
export function SizingResult({
  result: r,
}: {
  result: Schemas["SizingResultV1"];
}) {
  const valid = r.status === "VALID";
  return (
    <section
      className="panel sizing-result"
      aria-label="Canonical sizing result"
    >
      <h2>
        {valid
          ? "Policy-qualified sizing"
          : "Policy-qualified size unavailable"}
      </h2>
      {!valid && (
        <p>
          Any calculated amounts are theoretical only. Required controls have
          not all passed.
        </p>
      )}
      <div className="metric-grid">
        {r.base_risk_dollars != null && (
          <Metric
            label="Base dollar risk budget"
            value={money(r.base_risk_dollars)}
          />
        )}
        <Metric
          label="Allowed regime-adjusted budget"
          value={money(r.allowed_risk_dollars)}
        />
        {r.stop_distance != null && (
          <Metric
            label="Proposed stop distance"
            value={money(r.stop_distance)}
          />
        )}
      </div>
      {!valid && (
        <p className="inline-warning">
          {r.inputs.regime.eligible
            ? ""
            : "Market regime does not authorize this proposal. "}
          {r.inputs.earnings.eligibility === "CLEAR"
            ? ""
            : "Earnings clearance is unavailable or blocked."}
        </p>
      )}
      <div className="size-columns">
        {(
          [
            ["Risk-based", r.risk_based],
            ["Capital-constrained", r.capital_constrained],
          ] as const
        ).map(([name, size]) =>
          size ? (
            <section key={name}>
              <h3>
                {name} {valid ? "" : "· theoretical"}
              </h3>
              <dl>
                <dt>Whole shares</dt>
                <dd>{number(size.shares, 0)}</dd>
                <dt>Pilot shares</dt>
                <dd>{number(size.pilot_shares, 0)}</dd>
                <dt>Position cost</dt>
                <dd>{money(size.position_cost)}</dd>
                <dt>Planned dollar risk</dt>
                <dd>{money(size.planned_risk_dollars)}</dd>
                <dt>Equity risk</dt>
                <dd>{number(size.equity_risk_percent, 3)}%</dd>
              </dl>
            </section>
          ) : null,
        )}
      </div>
      <details>
        <summary>Complete sizing evidence</summary>
        <Reasons reasons={r.reasons} />
        <p>
          Stop distance {number(r.stop_distance_percent)}% of entry ·{" "}
          {number(r.stop_distance_atr)} ATR. Affordable shares{" "}
          {number(r.affordable_shares, 0)}.
        </p>
      </details>
    </section>
  );
}
export function Sizer({
  initialSymbol,
  initialDirection = "LONG",
}: {
  initialSymbol: string;
  initialDirection?: Direction;
}) {
  const [form, setForm] = useState({
    symbol: initialSymbol,
    direction: initialDirection,
    account_equity: "",
    available_buying_power: "",
    entry: "",
    stop: "",
  });
  const [searching, setSearching] = useState(false);
  const search = useQuery({
    queryKey: ["symbol-search", form.symbol],
    queryFn: () =>
      get<Schemas["SymbolSearchV1"][]>(
        "/research/symbols?" +
          new URLSearchParams({ q: form.symbol, limit: "10" }),
        undefined,
        "v2",
      ),
    enabled: searching,
  });
  const health = useQuery({
    queryKey: ["research-health"],
    queryFn: () =>
      get<Schemas["ResearchHealthV1"]>("/research/health", undefined, "v2"),
  });
  const mutation = useMutation({
    mutationFn: (body: Schemas["SizerRequestV1"]) =>
      get<Schemas["SizerResponseV1"]>("/sizer", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSearching(false);
    const numeric = (v: string) => (v === "" ? null : Number(v));
    mutation.mutate({
      symbol: form.symbol,
      direction: form.direction,
      account_equity: numeric(form.account_equity),
      available_buying_power: numeric(form.available_buying_power),
      entry: numeric(form.entry),
      stop: numeric(form.stop),
    });
  };
  return (
    <>
      <PageTitle eyebrow="PROPOSAL → RISK" title="Sizer">
        <span className="muted">What-if only · no orders</span>
      </PageTitle>
      <div className="sizer-layout">
        <section className="panel">
          <h2>Enter trade details</h2>
          <p>
            Account equity sets your risk budget; buying power limits what you
            can afford.
          </p>
          <form className="sizer-form" onSubmit={submit}>
            <label>
              Symbol search
              <input
                required
                value={form.symbol}
                onFocus={() => setSearching(true)}
                onChange={(e) => {
                  setForm({ ...form, symbol: e.target.value });
                  setSearching(true);
                  mutation.reset();
                }}
                placeholder="Ticker or company"
                autoComplete="off"
              />
            </label>
            {searching && search.data && (
              <ul className="symbol-results" aria-label="Symbol matches">
                {search.data.map((s) => (
                  <li key={s.symbol}>
                    <button
                      type="button"
                      onClick={() => {
                        setForm({ ...form, symbol: s.symbol });
                        setSearching(false);
                      }}
                    >
                      {s.symbol} · {s.name}
                    </button>
                  </li>
                ))}
                {search.data.length === 0 && (
                  <li>No matching snapshot symbol.</li>
                )}
              </ul>
            )}
            <label>
              Direction
              <select
                value={form.direction}
                onChange={(e) => {
                  setForm({ ...form, direction: e.target.value as Direction });
                  mutation.reset();
                }}
              >
                <option>LONG</option>
                <option>SHORT</option>
              </select>
            </label>
            {(
              [
                ["account_equity", "Account equity ($)"],
                ["available_buying_power", "Available buying power ($)"],
                ["entry", "Proposed entry ($)"],
                ["stop", "Proposed stop ($)"],
              ] as const
            ).map(([key, name]) => (
              <label key={key}>
                {name}
                <input
                  required
                  type="number"
                  min="0.000001"
                  step="any"
                  value={form[key]}
                  onChange={(e) => {
                    setForm({ ...form, [key]: e.target.value });
                    mutation.reset();
                  }}
                />
              </label>
            ))}
            <p className="risk-budget">
              Canonical base risk:{" "}
              {health.data
                ? number(health.data.risk_fraction * 100, 3) +
                  "% of account equity"
                : "Loading policy…"}
              . Applied risk:{" "}
              {health.data?.allowed_risk_fraction == null
                ? "Unavailable"
                : number(health.data.allowed_risk_fraction * 100, 3) + "%"}
              . Regime multiplier:{" "}
              {health.data?.regime_multiplier == null
                ? "Unavailable"
                : number(health.data.regime_multiplier, 2) + "×"}
              .
            </p>
            <p className="muted">
              Entry and stop are explicit user proposals. Setup invalidation is
              not a trade stop. Exact symbol/direction evidence is required.
            </p>
            <button
              className="primary-button"
              type="submit"
              disabled={mutation.isPending}
            >
              {mutation.isPending ? "Calculating…" : "Calculate size"}
            </button>
          </form>
        </section>
        <div>
          {mutation.error ? (
            <ErrorPanel error={mutation.error} />
          ) : mutation.data ? (
            <SizingResult result={mutation.data.result} />
          ) : (
            <StatePanel
              title={
                mutation.isPending ? "Calculating size" : "Enter trade details"
              }
            >
              A complete proposal is needed before sizing. No size is
              manufactured when market or earnings controls are unavailable.
            </StatePanel>
          )}
        </div>
      </div>
    </>
  );
}
