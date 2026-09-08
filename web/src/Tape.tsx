import { useQuery } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import { Chip, ErrorPanel, PageTitle, money, number } from "./ui";
import { label, type Row, type Direction } from "./research";
export interface Filters {
  action: string;
  direction: Direction;
  min_rs_comp: string;
  min_rs_rotation: string;
  veto: string;
  structure: string;
  setup: string;
  group: string;
  sort: string;
  order: "asc" | "desc";
  page: number;
}
export const initialFilters: Filters = {
  action: "",
  direction: "LONG",
  min_rs_comp: "",
  min_rs_rotation: "",
  veto: "",
  structure: "",
  setup: "",
  group: "",
  sort: "symbol",
  order: "asc",
  page: 1,
};
export function tapeQuery(f: Filters) {
  const q = new URLSearchParams({
    direction: f.direction,
    page: String(f.page),
    sort: f.sort,
    descending: String(f.order === "desc"),
  });
  for (const k of [
    "action",
    "structure",
    "setup",
    "group",
    "min_rs_comp",
    "min_rs_rotation",
    "veto",
  ] as const)
    if (f[k]) q.set(k, f[k]);
  return "/research/tape?" + q;
}
export function StockRows({
  rows,
  onSelect,
  onGroup,
}: {
  rows: Row[];
  onSelect: (symbol: string, direction?: Direction) => void;
  onGroup?: (id: string) => void;
}) {
  return (
    <tbody>
      {rows.map((r) => (
        <tr key={r.symbol + "|" + r.direction}>
          <td>
            <button
              className="symbol-link"
              onClick={() => onSelect(r.symbol, r.direction as Direction)}
            >
              {r.symbol}
            </button>
            <span className="cell-secondary">{r.direction}</span>
          </td>
          <td>{money(r.price)}</td>
          <td>{number(r.RS_comp, 0)}</td>
          <td>
            <Chip value={r.structure} />
          </td>
          <td className="setup-cell">
            {r.current_setup.setup ? (
              <>
                {label(r.current_setup.setup.family)} ·{" "}
                {label(r.current_setup.setup.status)}
              </>
            ) : (
              <span className="muted">
                {r.current_setup.state === "NONE"
                  ? "No current setup"
                  : "Evaluation unavailable"}
              </span>
            )}
          </td>
          <td>
            <Chip value={r.decision} />
          </td>
          <td className="group-cell">
            {r.industry && onGroup ? (
              <button
                title={`${r.industry.parent} · rank ${r.industry.rank ?? "unavailable"} / ${r.industry.eligible_count}`}
                onClick={() => onGroup(r.industry!.group_id)}
              >
                {r.industry.name}
              </button>
            ) : (
              (r.industry?.name ?? "Industry unavailable")
            )}
          </td>
          <td className="blocker-cell" title={r.primary_blocker?.detail}>
            {r.primary_blocker?.title ?? "All decision gates passed"}
          </td>
        </tr>
      ))}
    </tbody>
  );
}
export function Tape({
  filters: f,
  onFilters,
  onSelect,
  onGroup,
  enabled = true,
}: {
  filters: Filters;
  onFilters: (f: Filters) => void;
  onSelect: (s: string, direction?: Direction) => void;
  onGroup?: (id: string) => void;
  enabled?: boolean;
}) {
  const query = useQuery({
    queryKey: ["research-tape", f],
    queryFn: () =>
      get<Schemas["ResearchTapeV1"]>(tapeQuery(f), undefined, "v2"),
    enabled,
  });
  const update = (key: keyof Filters, value: string) =>
    onFilters({ ...f, [key]: value, page: 1 });
  const sort = (key: string) =>
    onFilters({
      ...f,
      sort: key,
      order: f.sort === key && f.order === "asc" ? "desc" : "asc",
      page: 1,
    });
  return (
    <>
      <PageTitle eyebrow="STOCK RESEARCH" title="Research tape">
        <label>
          Tape direction{" "}
          <select
            aria-label="Tape direction"
            value={f.direction}
            onChange={(e) => update("direction", e.target.value)}
          >
            <option>LONG</option>
            <option>SHORT</option>
          </select>
        </label>
      </PageTitle>
      <div className="filters">
        {(
          [
            ["action", "Decision", ["NONE", "WATCH", "TRADE", "ACT"]],
            [
              "structure",
              "Structure",
              ["NEUTRAL", "EMERGING", "UPTREND", "DETERIORATING", "DECLINE"],
            ],
            [
              "setup",
              "Current setup",
              ["EP", "CONTRACTION", "TREND_PULLBACK", "RANGE"],
            ],
          ] as const
        ).map(([key, name, options]) => (
          <label key={key}>
            {name}
            <select
              value={f[key]}
              onChange={(e) => update(key, e.target.value)}
            >
              <option value="">All</option>
              {options.map((v) => (
                <option key={v} value={v}>
                  {label(v)}
                </option>
              ))}
            </select>
          </label>
        ))}
        {(
          [
            ["min_rs_comp", "Min RS"],
            ["min_rs_rotation", "Min rotation RS"],
          ] as const
        ).map(([key, title]) => (
          <label key={key}>
            {title}
            <input
              type="number"
              min="0"
              max="100"
              value={f[key]}
              onChange={(e) => update(key, e.target.value)}
            />
          </label>
        ))}
        <label>
          Stored vetoes
          <select
            value={f.veto}
            onChange={(e) => update("veto", e.target.value)}
          >
            <option value="">All</option>
            <option value="true">Has vetoes</option>
            <option value="false">No vetoes</option>
          </select>
        </label>
        {f.group && (
          <button onClick={() => update("group", "")}>
            Clear group filter
          </button>
        )}
        <button onClick={() => onFilters(initialFilters)}>Reset filters</button>
      </div>
      {query.error ? (
        <ErrorPanel error={query.error} />
      ) : (
        <>
          <div className="list-caption">
            {query.data?.total ?? "…"} symbol/direction records · current one
            current setup per direction
          </div>
          <div className="table-scroll research-table">
            <table aria-label="Research tape">
              <thead>
                <tr>
                  {[
                    ["symbol", "Symbol"],
                    ["price", "Price"],
                    ["RS_comp", "RS"],
                    ["", "Structure"],
                    ["", "Current setup"],
                    ["decision", "Stored decision"],
                    ["", "Industry"],
                    ["", "Primary blocker"],
                  ].map(([key, title]) => (
                    <th key={title}>
                      {key ? (
                        <button
                          aria-label={"Sort by " + title}
                          onClick={() => sort(key)}
                        >
                          {title}{" "}
                          {f.sort === key
                            ? f.order === "asc"
                              ? "↑"
                              : "↓"
                            : ""}
                        </button>
                      ) : (
                        title
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <StockRows
                rows={query.data?.rows ?? []}
                onSelect={onSelect}
                onGroup={onGroup}
              />
            </table>
          </div>
          {query.data?.total === 0 && (
            <p className="empty-inline">No stocks match these filters.</p>
          )}
          <div className="pagination">
            <span>
              Page {f.page} of {query.data?.pages || 1}
            </span>
            <button
              disabled={f.page === 1}
              onClick={() => onFilters({ ...f, page: f.page - 1 })}
            >
              Previous
            </button>
            <button
              disabled={!query.data || f.page >= query.data.pages}
              onClick={() => onFilters({ ...f, page: f.page + 1 })}
            >
              Next
            </button>
          </div>
        </>
      )}
    </>
  );
}
