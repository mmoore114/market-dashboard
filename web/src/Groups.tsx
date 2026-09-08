import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import { ErrorPanel, PageTitle, number } from "./ui";
import {
  levels,
  levelNames,
  groupName,
  label,
  type Direction,
} from "./research";
import { StockRows } from "./Tape";
export function Groups({
  onSelect = () => {},
  onTape,
  initialGroup = null,
  enabled = true,
}: {
  onSelect?: (symbol: string, direction?: Direction) => void;
  onTape?: (id: string) => void;
  initialGroup?: { id: string; kind: string } | null;
  enabled?: boolean;
}) {
  const [kind, setKind] = useState("INDUSTRY");
  const [q, setQ] = useState("");
  const [all, setAll] = useState(false);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("leadership_rank");
  const [descending, setDescending] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [memberPage, setMemberPage] = useState(1);
  useEffect(() => {
    if (initialGroup) {
      setKind(initialGroup.kind);
      setSelected(initialGroup.id);
      setMemberPage(1);
    }
  }, [initialGroup]);
  const params = new URLSearchParams({
    kind,
    q,
    page: String(page),
    include_unranked: String(all),
    sort,
    descending: String(descending),
  });
  const query = useQuery({
    queryKey: ["ranked-groups", params.toString()],
    queryFn: () =>
      get<Schemas["ResearchGroupsV1"]>(
        "/research/groups?" + params,
        undefined,
        "v2",
      ),
    enabled,
  });
  const health = useQuery({
    queryKey: ["research-health"],
    queryFn: () =>
      get<Schemas["ResearchHealthV1"]>("/research/health", undefined, "v2"),
    enabled,
  });
  const memberParams = new URLSearchParams({
    kind,
    group_id: selected ?? "",
    page: String(memberPage),
  });
  const members = useQuery({
    queryKey: ["members", memberParams.toString()],
    queryFn: () =>
      get<Schemas["ResearchMembersV1"]>(
        "/research/members?" + memberParams,
        undefined,
        "v2",
      ),
    enabled: enabled && !!selected,
  });
  const sorting = (key: string) => {
    setDescending(
      sort === key ? !descending : key !== "leadership_rank" && key !== "name",
    );
    setSort(key);
    setPage(1);
  };
  return (
    <>
      <PageTitle eyebrow="GROUP LEADERSHIP" title="Groups">
        <span className="muted">
          Industry leadership · ranks compare eligible peers at one level
        </span>
      </PageTitle>
      <div className="level-tabs" aria-label="Group levels">
        {levels.map((k, i) => (
          <button
            key={k}
            aria-pressed={kind === k}
            onClick={() => {
              setKind(k);
              setPage(1);
              setSelected(null);
            }}
          >
            {levelNames[i]}
          </button>
        ))}
      </div>
      <div className="filters">
        <label>
          Find group
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
        </label>
        <label className="check-label">
          <input
            type="checkbox"
            checked={all}
            onChange={(e) => {
              setAll(e.target.checked);
              setPage(1);
            }}
          />
          Include unranked groups
        </label>
        <span className="source-age">
          {health.data?.membership_maintenance?.map((s) => (
            <span key={s.role}>
              {s.role === "hierarchy" ? "Hierarchy" : "Themes"} {s.age_days}d
              old · {label(s.reuse_status)}{" "}
            </span>
          ))}
        </span>
      </div>
      <details className="data-details">
        <summary>Membership & ranking details</summary>
        <p>
          Membership is an operator-approved dated capture, not provider
          reconfirmation. Parent paths remain distinct and themes may overlap.
          No historical rank movement is inferred.
        </p>
        <p>
          Rotation RS is a cross-sectional score. Rotation spread is RS rotation
          minus RS composite; it is not a change over time. WATCH/ACT counts are
          unique LONG stocks within each group; groups can overlap.
        </p>
        {health.data?.membership_maintenance?.map((s) => (
          <p key={s.role}>
            {s.role}: capture {s.capture_date}; reuse expires{" "}
            {s.expires_at ?? "Unavailable"};{" "}
            {s.reason ?? "Within approved reuse policy"}.
          </p>
        ))}
      </details>
      <div hidden={!!selected}>
        {query.error ? (
          <ErrorPanel error={query.error} />
        ) : (
          <>
            <div className="list-caption">
              {query.data?.total ?? "…"}{" "}
              {all ? "ranked and unranked" : "eligible ranked"} groups · rank 1
              leads
            </div>
            <div className="table-scroll research-table">
              <table aria-label="Ranked groups">
                <thead>
                  <tr>
                    {[
                      ["name", "Name"],
                      ["leadership_rank", "Leadership rank"],
                      ["median_RS_comp", "Median RS"],
                      ["median_RS_rotation", "Rotation RS"],
                      ["median_rotation_delta", "Rotation spread"],
                      ["valid_members", "Covered / total"],
                      ["watch_count", "WATCH / ACT"],
                    ].map(([key, title]) => (
                      <th key={key}>
                        <button onClick={() => sorting(key)}>
                          {title} {sort === key ? (descending ? "↓" : "↑") : ""}
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {query.data?.rows.map((g) => (
                    <tr key={g.group_id}>
                      <td className="group-name">
                        <button
                          onClick={() => {
                            setSelected(g.group_id);
                            setMemberPage(1);
                          }}
                        >
                          {g.name}
                        </button>
                        <small title={g.parent}>{g.parent}</small>
                      </td>
                      <td>
                        {g.leadership_rank == null ? (
                          <span title={g.reasons.map(label).join("; ")}>
                            Unranked
                            <small>
                              {g.reasons.length
                                ? label(g.reasons[0])
                                : "Insufficient ranking evidence"}
                            </small>
                          </span>
                        ) : (
                          <>
                            {number(g.leadership_rank, 0)} /{" "}
                            {g.eligible_group_count}
                          </>
                        )}
                      </td>
                      <td>{number(g.median_RS_comp)}</td>
                      <td>{number(g.median_RS_rotation)}</td>
                      <td>{number(g.median_rotation_delta)}</td>
                      <td>
                        {g.valid_members} / {g.total_members}
                      </td>
                      <td>
                        {g.watch_count} / {g.act_count}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {query.data?.total === 0 && (
              <p className="empty-inline">
                No eligible groups at this level. Include unranked groups to
                inspect coverage.
              </p>
            )}
            <div className="pagination">
              <span>
                Page {page} of {query.data?.pages || 1}
              </span>
              <button disabled={page === 1} onClick={() => setPage(page - 1)}>
                Previous groups
              </button>
              <button
                disabled={!query.data || page >= query.data.pages}
                onClick={() => setPage(page + 1)}
              >
                Next groups
              </button>
            </div>
          </>
        )}
      </div>
      {selected && (
        <section className="member-panel">
          <header className="panel-header">
            <div>
              <button onClick={() => setSelected(null)}>
                ← Back to ranked groups
              </button>
              <h2>{groupName(selected)}</h2>
              {onTape && (
                <button onClick={() => onTape(selected)}>
                  Open members on Tape →
                </button>
              )}
              <small className="muted">
                {members.data?.total ?? "…"} published members · bounded pages
              </small>
            </div>
          </header>
          {members.error ? (
            <ErrorPanel error={members.error} />
          ) : (
            <>
              <div className="table-scroll research-table">
                <table aria-label="Group members">
                  <thead>
                    <tr>
                      {[
                        "Symbol",
                        "Price",
                        "RS",
                        "Structure",
                        "Active setup",
                        "Decision",
                        "Sub-industry",
                        "Primary blocker",
                      ].map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <StockRows
                    rows={
                      members.data?.members.flatMap((m) =>
                        m.row ? [m.row] : [],
                      ) ?? []
                    }
                    onSelect={onSelect}
                  />
                  {members.data?.members.some((m) => !m.row) && (
                    <tbody>
                      {members.data.members
                        .filter((m) => !m.row)
                        .map((m) => (
                          <tr key={m.symbol}>
                            <td>{m.symbol}</td>
                            <td colSpan={7} className="muted">
                              {m.reason}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  )}
                </table>
              </div>
              <div className="pagination">
                <span>
                  Page {memberPage} of {members.data?.pages || 1}
                </span>
                <button
                  disabled={memberPage === 1}
                  onClick={() => setMemberPage(memberPage - 1)}
                >
                  Previous members
                </button>
                <button
                  disabled={!members.data || memberPage >= members.data.pages}
                  onClick={() => setMemberPage(memberPage + 1)}
                >
                  Next members
                </button>
              </div>
            </>
          )}
        </section>
      )}
    </>
  );
}
export function History() {
  return (
    <>
      <PageTitle eyebrow="PLANNED" title="Time Machine" />
      <p>
        Historical research is unavailable. Current membership captures cannot
        establish historical membership or past rotation. No historical snapshot
        is configured.
      </p>
      <a href="#brief">Return to daily research</a>
    </>
  );
}
