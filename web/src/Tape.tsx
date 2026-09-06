import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { get, type Schemas, type TapeRow } from "./api";
import { Chip, ErrorPanel, PageTitle, StatePanel, number, money } from "./ui";

export interface Filters {
  action: string;
  structure: string;
  setup: string;
  min_rs_comp: string;
  min_rs_rotation: string;
  group: string;
  veto: string;
  sort: string;
  order: "asc" | "desc";
  page: number;
  density: "compact" | "comfortable";
}
export const initialFilters: Filters = {
  action: "",
  structure: "",
  setup: "",
  min_rs_comp: "",
  min_rs_rotation: "",
  group: "",
  veto: "",
  sort: "symbol",
  order: "asc",
  page: 1,
  density: "compact",
};
export function tapeQuery(filters: Filters) {
  const q = new URLSearchParams({
    page: String(filters.page),
    page_size: "25",
    sort: filters.sort,
    order: filters.order,
  });
  for (const k of [
    "action",
    "structure",
    "setup",
    "min_rs_comp",
    "min_rs_rotation",
    "group",
    "veto",
  ] as const)
    if (filters[k]) q.set(k, filters[k]);
  return `/tape?${q}`;
}
export function Tape({
  filters: f,
  onFilters,
  onSelect,
}: {
  filters: Filters;
  onFilters: (filters: Filters) => void;
  onSelect: (symbol: string) => void;
}) {
  const query = useQuery({
    queryKey: ["tape", f],
    queryFn: () => get<Schemas["TapeV1"]>(tapeQuery(f)),
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
  const columns = useMemo<ColumnDef<TapeRow>[]>(
    () => [
      {
        id: "symbol",
        header: "Symbol",
        cell: ({ row }) => (
          <>
            <button
              className="symbol-link"
              onClick={() => onSelect(row.original.symbol)}
            >
              {row.original.symbol}
            </button>
            <small>{row.original.direction}</small>
          </>
        ),
      },
      {
        id: "price",
        header: "Price",
        cell: ({ row }) => money(row.original.price),
      },
      {
        id: "structure",
        header: "Structure",
        cell: ({ row }) => <Chip value={row.original.structure} />,
      },
      {
        id: "RS_comp",
        header: "RS comp",
        cell: ({ row }) => number(row.original.RS_comp),
      },
      {
        id: "return_5",
        header: "5 sessions",
        cell: ({ row }) => (
          <>
            {row.original.return_5 == null
              ? "Unknown"
              : `${number(row.original.return_5 * 100, 2)}%`}
            <small>p{number(row.original.percentile_5)}</small>
          </>
        ),
      },
      {
        id: "return_21",
        header: "21 sessions",
        cell: ({ row }) => (
          <>
            {row.original.return_21 == null
              ? "Unknown"
              : `${number(row.original.return_21 * 100, 2)}%`}
            <small>p{number(row.original.percentile_21)}</small>
          </>
        ),
      },
      {
        id: "RS_rotation",
        header: "RS rotation",
        cell: ({ row }) => number(row.original.RS_rotation),
      },
      {
        id: "rotation_delta",
        header: "Delta",
        cell: ({ row }) => number(row.original.rotation_delta),
      },
      {
        id: "group_rank",
        header: "Sub-industry",
        cell: ({ row }) => (
          <>
            {row.original.sub_industry ?? "Unknown"}
            <small>Rank {number(row.original.group_rank)}</small>
          </>
        ),
      },
      {
        id: "setups",
        header: "Setups",
        cell: ({ row }) => (
          <>
            {row.original.setups.length
              ? row.original.setups.map((s) => (
                  <span className="setup-line" key={s.setup_id}>
                    {s.family.replaceAll("_", " ")}
                    <small>
                      {s.direction} · {s.status.replaceAll("_", " ")}
                    </small>
                  </span>
                ))
              : "None supplied"}
          </>
        ),
      },
      {
        id: "extension_atr",
        header: "Extension",
        cell: ({ row }) => `${number(row.original.extension_atr, 2)} ATR`,
      },
      {
        id: "decision",
        header: "Decision",
        cell: ({ row }) => <Chip value={row.original.decision} />,
      },
      {
        id: "earnings",
        header: "Earnings",
        cell: ({ row }) => <Chip value={row.original.earnings} />,
      },
      {
        id: "reasons",
        header: "Veto / status",
        cell: ({ row }) => (
          <span className="veto-summary">
            {row.original.has_veto
              ? `${row.original.reasons.length} reasons · ${row.original.reasons[0]?.explanation}`
              : "All gates passed"}
          </span>
        ),
      },
    ],
    [onSelect],
  );
  const table = useReactTable({
    data: query.data?.rows ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
  });
  const sortable = [
    "symbol",
    "price",
    "RS_comp",
    "RS_rotation",
    "rotation_delta",
    "extension_atr",
    "decision",
    "group_rank",
  ];
  return (
    <>
      <PageTitle eyebrow="GROUPS / TAPE" title="Research tape">
        <label className="density-label">
          Density
          <select
            value={f.density}
            onChange={(e) => update("density", e.target.value)}
          >
            <option value="compact">Compact</option>
            <option value="comfortable">Comfortable</option>
          </select>
        </label>
      </PageTitle>
      <section className="filters" aria-label="Tape filters">
        <label>
          Decision
          <select
            value={f.action}
            onChange={(e) => update("action", e.target.value)}
          >
            <option value="">All states</option>
            {["NONE", "WATCH", "TRADE", "ACT"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Structure
          <select
            value={f.structure}
            onChange={(e) => update("structure", e.target.value)}
          >
            <option value="">All structures</option>
            {["NEUTRAL", "EMERGING", "UPTREND", "DETERIORATING", "DECLINE"].map(
              (s) => (
                <option key={s}>{s}</option>
              ),
            )}
          </select>
        </label>
        <label>
          Setup family
          <select
            value={f.setup}
            onChange={(e) => update("setup", e.target.value)}
          >
            <option value="">All families</option>
            {["EP", "CONTRACTION", "TREND_PULLBACK", "RANGE"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Min RS comp
          <input
            type="number"
            min="0"
            max="100"
            value={f.min_rs_comp}
            onChange={(e) => update("min_rs_comp", e.target.value)}
          />
        </label>
        <label>
          Min RS rotation
          <input
            type="number"
            min="0"
            max="100"
            value={f.min_rs_rotation}
            onChange={(e) => update("min_rs_rotation", e.target.value)}
          />
        </label>
        <label>
          Exact sub-industry
          <input
            value={f.group}
            onChange={(e) => update("group", e.target.value)}
            placeholder="All groups"
          />
        </label>
        <label>
          Veto presence
          <select
            value={f.veto}
            onChange={(e) => update("veto", e.target.value)}
          >
            <option value="">All rows</option>
            <option value="true">Has veto</option>
            <option value="false">No veto</option>
          </select>
        </label>
        <button
          className="text-button"
          onClick={() => onFilters(initialFilters)}
        >
          Reset filters
        </button>
      </section>
      {query.isPending ? (
        <StatePanel title="Loading Tape">Reading candidate rows…</StatePanel>
      ) : query.error ? (
        <ErrorPanel error={query.error} retry={() => void query.refetch()} />
      ) : (
        <section className={`panel tape-panel ${f.density}`}>
          <div className="table-toolbar">
            <span>{query.data.total} symbol/direction records</span>
            <span>
              Null values stay unknown · select a symbol to inspect evidence
            </span>
          </div>
          {query.data.rows.length === 0 ? (
            <StatePanel title="No matching candidates">
              Adjust the filters to see more records.
            </StatePanel>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  {table.getHeaderGroups().map((g) => (
                    <tr key={g.id}>
                      {g.headers.map((h) => (
                        <th
                          key={h.id}
                          aria-sort={
                            f.sort === h.id
                              ? f.order === "asc"
                                ? "ascending"
                                : "descending"
                              : undefined
                          }
                        >
                          {sortable.includes(h.id) ? (
                            <button
                              onClick={() => sort(h.id)}
                              aria-label={`Sort by ${String(h.column.columnDef.header)}`}
                            >
                              {flexRender(
                                h.column.columnDef.header,
                                h.getContext(),
                              )}{" "}
                              <span>
                                {f.sort === h.id
                                  ? f.order === "asc"
                                    ? "↑"
                                    : "↓"
                                  : "↕"}
                              </span>
                            </button>
                          ) : (
                            flexRender(
                              h.column.columnDef.header,
                              h.getContext(),
                            )
                          )}
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => (
                    <tr
                      key={`${row.original.symbol}-${row.original.direction}`}
                    >
                      {row.getVisibleCells().map((c) => (
                        <td key={c.id}>
                          {flexRender(c.column.columnDef.cell, c.getContext())}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="pagination">
            <span>
              Page {query.data.page} of {Math.max(1, query.data.pages)}
            </span>
            <div>
              <button
                disabled={f.page <= 1}
                onClick={() => onFilters({ ...f, page: f.page - 1 })}
              >
                Previous
              </button>
              <button
                disabled={f.page >= query.data.pages}
                onClick={() => onFilters({ ...f, page: f.page + 1 })}
              >
                Next
              </button>
            </div>
          </div>
        </section>
      )}
    </>
  );
}
