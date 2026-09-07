import { useQuery } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import { Chip, ErrorPanel, PageTitle, StatePanel, number } from "./ui";

export function Brief({ onSelect }: { onSelect: (symbol: string) => void }) {
  const query = useQuery({
    queryKey: ["brief"],
    queryFn: () => get<Schemas["BriefV1"]>("/brief"),
  });
  if (query.isPending)
    return (
      <StatePanel title="Loading daily brief">
        Reading regime and decision evidence…
      </StatePanel>
    );
  if (query.error)
    return (
      <ErrorPanel error={query.error} retry={() => void query.refetch()} />
    );
  const d = query.data;
  return (
    <>
      <PageTitle eyebrow="MARKET CONTEXT" title="Daily brief">
        <span className="session-tag">
          {d.meta.as_of_session} <span>→</span> {d.meta.action_session}
        </span>
      </PageTitle>
      <section className="regime-panel" aria-label="Market regime">
        <div className="regime-heading">
          <div>
            <span className="eyebrow">CONFIRMED REGIME</span>
            <h2>
              <Chip value={d.regime_state} /> Market context
            </h2>
            <p>
              {d.regime_reason.replaceAll("_", " ").toLowerCase()} · evaluated
              for the action session shown
            </p>
          </div>
          <span className="regime-glyph" aria-hidden="true">
            ◈
          </span>
        </div>
        <div className="sleeves">
          {d.sleeves.map((s) => (
            <div key={s.name}>
              <span>
                {s.name === "index"
                  ? "Index structure"
                  : s.name === "internals"
                    ? "Leadership internals"
                    : s.name[0].toUpperCase() + s.name.slice(1)}
              </span>
              <Chip value={s.state} />
              <small>
                {s.score == null
                  ? "No score — unknown inputs"
                  : `Sleeve vote ${s.score > 0 ? "+" : ""}${s.score}`}
              </small>
            </div>
          ))}
        </div>
      </section>
      {d.denominators && (
        <section className="panel" aria-label="Current cohort denominators">
          <h2>Current cohort evidence counts</h2>
          {d.denominators.map((v) => (
            <p key={v.name}>
              {v.name}: {v.numerator ?? "UNKNOWN"} qualifying / {v.valid_count}{" "}
              valid / {v.population_count} population
            </p>
          ))}
          {d.sleeves
            .filter((s) => s.reasons.length)
            .map((s) => (
              <p key={s.name}>
                {s.name}: {s.reasons.join(", ")}
              </p>
            ))}
        </section>
      )}
      <section className="funnel" aria-label="Decision funnel">
        {(["NONE", "WATCH", "TRADE", "ACT"] as const).map((s, i) => (
          <div key={s}>
            <span className="eyebrow">
              0{i + 1} / {s === "NONE" ? "OUTSIDE LADDER" : s}
            </span>
            <strong>{d.funnel[s]}</strong>
            <span>
              {
                [
                  "Not yet qualified",
                  "Strength to follow",
                  "Context qualifies",
                  "Discretionary review",
                ][i]
              }
            </span>
          </div>
        ))}
      </section>
      <section className="panel">
        <header className="panel-header">
          <div>
            <span className="eyebrow">DECISION QUEUE</span>
            <h2>
              Ready for review{" "}
              <span className="count">{d.act_candidates.length}</span>
            </h2>
          </div>
          <a href="#tape">Open Tape →</a>
        </header>
        {d.act_candidates.length === 0 ? (
          <StatePanel title="No ACT candidates">
            No symbol passed every required gate in this snapshot.
          </StatePanel>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qualifying setups</th>
                  <th>RS comp</th>
                  <th>Rotation</th>
                  <th>Extension</th>
                  <th>Sub-industry</th>
                  <th>Context</th>
                </tr>
              </thead>
              <tbody>
                {d.act_candidates.map((r) => (
                  <tr key={`${r.symbol}-${r.direction}`}>
                    <td>
                      <button
                        className="symbol-link"
                        onClick={() => onSelect(r.symbol)}
                      >
                        {r.symbol}
                      </button>
                      <small>{r.display_name}</small>
                    </td>
                    <td>
                      {r.setups
                        .filter((s) => s.act_eligible)
                        .map((s) => (
                          <span className="setup-tag" key={s.setup_id}>
                            {s.family.replaceAll("_", " ")}
                          </span>
                        ))}
                    </td>
                    <td>{number(r.RS_comp)}</td>
                    <td>{number(r.RS_rotation)}</td>
                    <td>{number(r.extension_atr, 2)} ATR</td>
                    <td>{r.sub_industry ?? "Unknown"}</td>
                    <td>
                      <Chip value={r.decision} />
                      <small>
                        {r.reasons[0]?.explanation ??
                          "All decision gates passed"}
                      </small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <div className="group-grid">
        {[
          ["Leading sub-industries", d.leading_groups],
          ["Weakening rotation", d.weakening_groups],
        ].map(([title, groups]) => (
          <section className="panel" key={title as string}>
            <header className="panel-header">
              <h2>{title as string}</h2>
              <span className="muted">Supplied group evidence</span>
            </header>
            {(groups as Schemas["GroupSummaryV1"][]).length ? (
              <ul className="group-list">
                {(groups as Schemas["GroupSummaryV1"][]).map((g) => (
                  <li key={g.group_id}>
                    <div>
                      <b>{g.group_id}</b>
                      <small>
                        Rank {number(g.leadership_rank)} /{" "}
                        {g.eligible_group_count}
                      </small>
                    </div>
                    <div>
                      <b>{number(g.median_RS_comp)}</b>
                      <small>
                        Median RS · Δ {number(g.median_rotation_delta)}
                      </small>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-inline">
                No qualifying group evidence supplied.
              </p>
            )}
          </section>
        ))}
      </div>
      <div className="portfolio-unavailable">
        <span>PORTFOLIO HEAT</span>
        <span>{d.portfolio_heat_status}</span>
      </div>
    </>
  );
}
