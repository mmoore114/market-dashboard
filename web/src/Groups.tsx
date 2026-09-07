import { useQuery } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import { ErrorPanel, StatePanel } from "./ui";

export function Groups() {
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
      {query.data.groups.map((g) => (
        <details key={`${g.group_type}:${g.group_id}`}>
          <summary>
            {g.group_id} · {g.group_type}
          </summary>
          <p>
            Members {g.total_members}; valid RS {g.valid_RS_comp_count};
            coverage {g.coverage}
          </p>
          <p>{g.missing_context_reasons.join(", ")}</p>
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
