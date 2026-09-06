import { useQuery } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import { ErrorPanel, PageTitle, StatePanel } from "./ui";

export function Rules() {
  const query = useQuery({
    queryKey: ["rules"],
    queryFn: () => get<Schemas["RulesViewV1"]>("/rules"),
  });
  if (query.isPending)
    return (
      <StatePanel title="Loading rules">
        Reading current versioned hypotheses…
      </StatePanel>
    );
  if (query.error)
    return (
      <ErrorPanel error={query.error} retry={() => void query.refetch()} />
    );
  const d = query.data;
  return (
    <>
      <PageTitle eyebrow="TRANSPARENT BY DESIGN" title="Rules & evidence">
        <span className="hypothesis">{d.status}</span>
      </PageTitle>
      <p className="rules-intro">
        Current hypotheses returned by the Python API. Thresholds remain
        uncalibrated; every promotion retains its component evidence.
      </p>
      <div className="rules-grid">
        {d.sections.map((s) => (
          <section className="panel rule-section" key={s.title}>
            <h2>{s.title}</h2>
            <ul>
              {s.lines.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      <section className="panel version-panel">
        <h2>Exact version identities</h2>
        <dl>
          {Object.entries(d.versions).map(([key, value]) => (
            <div key={key}>
              <dt>{key.replaceAll("_", " ")}</dt>
              <dd>
                <code>{value}</code>
              </dd>
            </div>
          ))}
        </dl>
        <p>Foundation rules fingerprint</p>
        <code>{d.rules_fingerprint}</code>
        <p>Snapshot fingerprint</p>
        <code>{d.meta.fingerprint}</code>
      </section>
    </>
  );
}
