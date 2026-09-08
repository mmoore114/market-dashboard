import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import { ErrorPanel, StatePanel } from "./ui";

function displayPath(id: string) {
  try {
    const path: unknown = JSON.parse(id);
    if (Array.isArray(path))
      return path.map((v) => v ?? "Unknown parent").join(" / ");
  } catch {
    /* Older catalogs use plain labels. */
  }
  return id;
}

export function Groups() {
  const [kind, setKind] = useState("ALL");
  const [search, setSearch] = useState("");
  const query = useQuery({
    queryKey: ["groups"],
    queryFn: () => get<Schemas["GroupsViewV1"]>("/groups"),
  });
  if (query.error)
    return (
      <ErrorPanel error={query.error} retry={() => void query.refetch()} />
    );
  if (!query.data)
    return (
      <StatePanel title="Loading groups">
        Checking published group evidence.
      </StatePanel>
    );
  return (
    <section>
      <h1>Groups</h1>
      {query.data.reasons.map((r) => (
        <p key={r.code}>
          {r.explanation} <code>{r.code}</code>
        </p>
      ))}
      <p>
        Membership is a dated capture, not historical coverage. Hierarchy paths
        preserve conflicting parents. Themes may overlap; no theme assignment
        does not imply a confirmed exclusion.
      </p>
      {query.data.membership_maintenance?.map((source) => (
        <p key={`${source.role}:${source.capture_date}`}>
          {source.role === "hierarchy" ? "Hierarchy" : "Themes"} capture{" "}
          {source.capture_date}
          {" · "}
          {source.age_days} calendar days old · {source.reuse_status}
          {source.expires_at && <> · reuse expires {source.expires_at}</>}
          {source.warning_at && (
            <> · refresh warning from {source.warning_at}</>
          )}
          {" · "}Operator-approved reuse; Deepvue has not reconfirmed
          membership.
          {!source.applies_to_snapshot_capture && (
            <>
              {" "}
              Newer capture available; displayed snapshot requires rebuilding.
            </>
          )}
          {source.reason && (
            <span style={{ overflowWrap: "anywhere" }}> {source.reason}</span>
          )}
        </p>
      ))}
      <label>
        Group level{" "}
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="ALL">All levels</option>
          {["SECTOR", "GROUP", "INDUSTRY", "SUB_INDUSTRY", "THEME"].map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
      </label>
      <label>
        Find group{" "}
        <input value={search} onChange={(e) => setSearch(e.target.value)} />
      </label>
      {query.data.groups
        .filter(
          (g) =>
            (kind === "ALL" || g.group_type === kind) &&
            displayPath(g.group_id)
              .toLowerCase()
              .includes(search.toLowerCase()),
        )
        .map((g) => (
          <details key={`${g.group_type}:${g.group_id}`}>
            <summary>
              {displayPath(g.group_id)} · {g.group_type}
            </summary>
            <p>
              Members {g.total_members}; valid RS {g.valid_RS_comp_count};
              coverage {g.coverage}
            </p>
            <p>
              Source {g.membership.source_as_of_date}; effective{" "}
              {g.membership.effective_session}; known{" "}
              {g.membership.known_session}; valid through{" "}
              {g.membership.valid_through}.
            </p>
            {"analysis_basis" in g.membership && (
              <p>
                CURRENT COHORT · market evidence{" "}
                {g.membership.market_as_of_session}; membership known at{" "}
                {g.membership.known_at}; evaluated{" "}
                {g.membership.evaluation_timestamp}; action{" "}
                {g.membership.action_session}. Historical rotation changes
                unavailable.
              </p>
            )}
            <p>
              Median RS {g.median_RS_comp ?? "Unavailable"}; leadership rank{" "}
              {g.leadership_rank ?? "Unavailable"}; rotation rank{" "}
              {g.group_rotation_rank ?? "Unavailable"}.
            </p>
            <p>
              Outside research cohort {g.outside_universe_count}; excluded
              non-securities {g.excluded_non_security_count}.
            </p>
            <p>
              {[
                ...g.leadership_rank_reasons,
                ...g.rotation_rank_reasons,
                ...g.missing_context_reasons,
              ].join(", ")}
            </p>
            <ul>
              {g.members.map((m) => (
                <li key={m.source_symbol}>
                  {m.source_symbol}
                  {" · "}
                  {m.identity_reason}
                </li>
              ))}
            </ul>
          </details>
        ))}
    </section>
  );
}
export function History({ session }: { session: string }) {
  const query = useQuery({
    queryKey: ["history", session],
    queryFn: () => get<Schemas["ErrorV1"]>(`/time-machine/${session}`),
    retry: false,
  });
  return (
    <section>
      <h1>Time Machine</h1>
      {query.error ? (
        <ErrorPanel error={query.error} retry={() => void query.refetch()} />
      ) : (
        <p>Checking historical evidence availability.</p>
      )}
    </section>
  );
}
