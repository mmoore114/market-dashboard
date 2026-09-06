import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import {
  Chip,
  ErrorPanel,
  Metric,
  PageTitle,
  Reasons,
  money,
  number,
  StatePanel,
} from "./ui";

export function SizingResult({
  result: r,
}: {
  result: Schemas["SizingResultV1"];
}) {
  return (
    <section
      className="panel sizing-result"
      aria-label="Canonical sizing result"
    >
      <header className="panel-header">
        <h2>Canonical sizing result</h2>
        <Chip value={r.status} />
      </header>
      <div className="metric-grid">
        <Metric label="Base equity risk" value={money(r.base_risk_dollars)} />
        <Metric
          label="Allowed regime risk"
          value={money(r.allowed_risk_dollars)}
        />
        <Metric label="Stop distance" value={money(r.stop_distance)} />
        <Metric
          label="Stop distance / entry"
          value={`${number(r.stop_distance_percent, 2)}%`}
        />
        <Metric
          label="Stop distance / ATR"
          value={number(r.stop_distance_atr, 2)}
        />
        <Metric
          label="Affordable shares"
          value={number(r.affordable_shares, 0)}
        />
      </div>
      {r.status === "INVALID" && (
        <p className="inline-warning">
          Size refused. Any calculated amounts below are theoretical and are not
          an available size.
        </p>
      )}
      <div className="size-columns">
        {(
          [
            ["Risk-based", r.risk_based],
            ["Capital-constrained", r.capital_constrained],
          ] as const
        ).map(([label, size]) => (
          <div key={label}>
            <h3>{label}</h3>
            {size ? (
              <dl>
                <dt>Full shares</dt>
                <dd>{number(size.shares, 0)}</dd>
                <dt>Pilot shares</dt>
                <dd>{number(size.pilot_shares, 0)}</dd>
                <dt>Position cost</dt>
                <dd>{money(size.position_cost)}</dd>
                <dt>Pilot cost</dt>
                <dd>{money(size.pilot_position_cost)}</dd>
                <dt>Planned risk</dt>
                <dd>{money(size.planned_risk_dollars)}</dd>
                <dt>Pilot risk</dt>
                <dd>{money(size.pilot_risk_dollars)}</dd>
                <dt>Equity at risk</dt>
                <dd>{number(size.equity_risk_percent, 3)}%</dd>
                <dt>Pilot equity risk</dt>
                <dd>{number(size.pilot_equity_risk_percent, 3)}%</dd>
                <dt>Unused risk</dt>
                <dd>{money(size.unused_risk_dollars)}</dd>
                <dt>Pilot unused risk</dt>
                <dd>{money(size.pilot_unused_risk_dollars)}</dd>
              </dl>
            ) : (
              <p className="muted">
                Unavailable — inspect refusal reasons below.
              </p>
            )}
          </div>
        ))}
      </div>
      <Reasons reasons={r.reasons} />
    </section>
  );
}
export function Sizer({ initialSymbol }: { initialSymbol: string }) {
  const [form, setForm] = useState({
    symbol: initialSymbol,
    direction: "LONG" as "LONG" | "SHORT",
    account_equity: "25000",
    available_buying_power: "25000",
    entry: "",
    stop: "",
  });
  const mutation = useMutation({
    mutationFn: (body: Schemas["SizerRequestV1"]) =>
      get<Schemas["SizerResponseV1"]>("/sizer", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
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
      <PageTitle eyebrow="PER-IDEA RISK" title="Sizer">
        <span className="muted">What-if calculation · no orders</span>
      </PageTitle>
      <div className="sizer-layout">
        <section className="panel">
          <header className="panel-header">
            <h2>Proposed trade</h2>
          </header>
          <form className="sizer-form" onSubmit={submit}>
            <label>
              Exact symbol
              <input
                required
                value={form.symbol}
                onChange={(e) => setForm({ ...form, symbol: e.target.value })}
                placeholder="Exact snapshot symbol"
                autoCapitalize="off"
                autoComplete="off"
              />
            </label>
            <label>
              Direction
              <select
                value={form.direction}
                onChange={(e) =>
                  setForm({
                    ...form,
                    direction: e.target.value as "LONG" | "SHORT",
                  })
                }
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
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  step="any"
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                />
              </label>
            ))}
            <p className="muted">
              Entry and stop are your proposals. Earnings and regime context
              come from the current snapshot. Values stay in memory only.
            </p>
            {form.direction === "SHORT" && (
              <p className="inline-warning">
                SHORT is a sizing illustration. V1 decision promotion remains
                capped at WATCH.
              </p>
            )}
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
          {mutation.isPending ? (
            <StatePanel title="Calculating size">
              The canonical Python risk function is evaluating the proposal.
            </StatePanel>
          ) : mutation.error ? (
            <ErrorPanel error={mutation.error} />
          ) : mutation.data ? (
            <SizingResult result={mutation.data.result} />
          ) : (
            <StatePanel title="Make the risk explicit">
              Enter an exact symbol, entry and stop to review the canonical size
              and every refusal reason.
            </StatePanel>
          )}
        </div>
      </div>
    </>
  );
}
