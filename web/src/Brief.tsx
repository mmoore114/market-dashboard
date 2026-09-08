import type { Direction } from "./research";
import { useQuery } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import { Chip, ErrorPanel, PageTitle, StatePanel, number } from "./ui";
import { groupName, label } from "./research";
export function Brief({
  onSelect,
  onTape = () => {},
  onGroup = () => {},
}: {
  onSelect: (symbol: string, direction?: Direction) => void;
  onTape?: (action: string) => void;
  onGroup?: (id: string) => void;
}) {
  const query = useQuery({
    queryKey: ["brief"],
    queryFn: () => get<Schemas["BriefV1"]>("/brief"),
  });
  const health = useQuery({
    queryKey: ["research-health"],
    queryFn: () =>
      get<Schemas["ResearchHealthV1"]>("/research/health", undefined, "v2"),
  });
  if (query.error) return <ErrorPanel error={query.error} />;
  if (!query.data)
    return (
      <StatePanel title="Loading daily brief">
        Reading verified context…
      </StatePanel>
    );
  const d = query.data;
  return (
    <>
      <PageTitle eyebrow="MARKET → GROUPS → STOCKS" title="Daily brief" />
      <section className="regime-panel" aria-label="Market regime">
        <div className="regime-heading">
          <div>
            <h2>
              <Chip value={d.regime_state} /> Market context
            </h2>
            <p>
              {d.regime_state === "UNKNOWN"
                ? "Current evidence cannot confirm a regime. New-risk qualification remains unavailable."
                : "Confirmed market context applies to the displayed action session."}
            </p>
          </div>
        </div>
        <div className="sleeves">
          {d.sleeves.map((s) => (
            <div key={s.name}>
              <span>
                {s.name === "index"
                  ? "Index structure"
                  : s.name === "internals"
                    ? "Leadership internals"
                    : label(s.name)}
              </span>
              <Chip value={s.state} />
              <small>
                {s.score == null
                  ? "Evidence incomplete"
                  : `Sleeve vote ${s.score > 0 ? "+" : ""}${s.score}`}
              </small>
            </div>
          ))}
        </div>
        {health.data?.missing.length ? (
          <p className="data-health">
            Missing or incomplete: {health.data.missing.join(" · ")}.
          </p>
        ) : null}
        <details className="data-details">
          <summary>Market evidence details</summary>
          {d.denominators?.map((v) => (
            <p key={v.name}>
              {v.name}: {v.numerator ?? "Unknown"} qualifying / {v.valid_count}{" "}
              valid / {v.population_count} population
            </p>
          ))}
          {d.sleeves.map((s) => (
            <p key={s.name}>
              {label(s.name)}:{" "}
              {s.reasons.map(label).join("; ") || "No missing inputs reported"}
            </p>
          ))}
        </details>
      </section>
      <section className="funnel" aria-label="Decision funnel">
        {(["NONE", "WATCH", "TRADE", "ACT"] as const).map((s) => (
          <button
            key={s}
            onClick={() => onTape(s)}
            aria-label={`Open ${s} candidates`}
          >
            <span>{s}</span>
            <strong>{d.funnel[s]}</strong>
            <span>
              {
                {
                  NONE: "Not qualified",
                  WATCH: "Research candidates",
                  TRADE: "Context qualifies",
                  ACT: "Discretionary review",
                }[s]
              }{" "}
              →
            </span>
          </button>
        ))}
      </section>
      <section className="panel compact-queue">
        <header className="panel-header">
          <h2>Review queue</h2>
          <button onClick={() => onTape("WATCH")}>
            Explore {d.funnel.WATCH} WATCH candidates →
          </button>
        </header>
        {d.act_candidates.length ? (
          <div className="candidate-strip">
            {d.act_candidates.map((r) => (
              <button
                key={r.symbol + "|" + r.direction}
                onClick={() => onSelect(r.symbol, r.direction as Direction)}
              >
                {r.symbol} · {label(r.decision)}
              </button>
            ))}
          </div>
        ) : (
          <p>
            No ACT candidates: no stored decision passes every required gate.
            WATCH candidates remain available for research and chart review.
          </p>
        )}
      </section>
      <div className="group-grid">
        {[
          ["Leading sub-industries", d.leading_groups],
          ["Lower rotation than composite", d.weakening_groups],
        ].map(([title, groups]) => (
          <section className="panel" key={title as string}>
            <h2>{title as string}</h2>
            <p className="muted">
              Within sub-industries · rotation spread is cross-sectional, not
              historical movement
            </p>
            <ul className="group-list">
              {(groups as Schemas["GroupSummaryV1"][]).map((g) => (
                <li key={g.group_id}>
                  <button onClick={() => onGroup(g.group_id)}>
                    {groupName(g.group_id)}
                  </button>
                  <span>
                    Rank {number(g.leadership_rank, 0)} /{" "}
                    {g.eligible_group_count}
                    <small>
                      Median RS {number(g.median_RS_comp)} · spread{" "}
                      {number(g.median_rotation_delta)}
                    </small>
                  </span>
                </li>
              ))}
            </ul>
            {!(groups as unknown[]).length && (
              <p className="empty-inline">
                No eligible group evidence supplied.
              </p>
            )}
          </section>
        ))}
      </div>
    </>
  );
}
