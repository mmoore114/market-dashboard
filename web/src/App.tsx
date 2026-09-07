import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get, type Schemas } from "./api";
import { Context, ErrorPanel, StatePanel } from "./ui";
import { Brief } from "./Brief";
import { Tape, initialFilters, type Filters } from "./Tape";
import { Detail } from "./Detail";
import { Sizer } from "./Sizer";
import { Groups, History } from "./Groups";
import { Rules } from "./Rules";

const routes = [
  "brief",
  "tape",
  "groups",
  "sizer",
  "rules",
  "history",
] as const;
type Route = (typeof routes)[number];
function currentRoute(): Route {
  const value = window.location.hash.slice(1);
  return routes.includes(value as Route) ? (value as Route) : "brief";
}
function preferences(): { filters: Filters; selected: string | null } {
  try {
    const p = JSON.parse(sessionStorage.getItem("aperture-ui-v1") || "{}");
    return {
      filters: { ...initialFilters, ...p.filters },
      selected: typeof p.selected === "string" ? p.selected : null,
    };
  } catch {
    return { filters: initialFilters, selected: null };
  }
}
export function App() {
  const [route, setRoute] = useState<Route>(currentRoute);
  const [filters, setFilters] = useState<Filters>(() => preferences().filters);
  const [selected, setSelected] = useState<string | null>(
    () => preferences().selected,
  );
  const [sizerSymbol, setSizerSymbol] = useState("");
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => get<Schemas["HealthV1"]>("/health"),
    refetchInterval: 30000,
  });
  useEffect(() => {
    const handle = () => {
      setRoute(currentRoute());
      setSelected(null);
    };
    window.addEventListener("hashchange", handle);
    return () => window.removeEventListener("hashchange", handle);
  }, []);
  useEffect(() => {
    try {
      sessionStorage.setItem(
        "aperture-ui-v1",
        JSON.stringify({ filters, selected }),
      );
    } catch {
      /* Preferences are optional. */
    }
  }, [filters, selected]);
  const sizeSymbol = (symbol: string) => {
    setSizerSymbol(symbol);
    setSelected(null);
    window.location.hash = "sizer";
    setRoute("sizer");
  };
  const available = health.data?.available === true;
  return (
    <div className="workstation">
      <a className="skip-link" href="#main-content">
        Skip to research
      </a>
      <aside className="sidebar">
        <a href="#brief" className="brand">
          <span className="brand-mark">◈</span>
          <span>
            Aperture<small>RESEARCH WORKSTATION</small>
          </span>
        </a>
        <span className="nav-label">WORKSPACE</span>
        <nav aria-label="Primary navigation">
          {routes.map((r, i) => (
            <a
              key={r}
              href={`#${r}`}
              aria-current={route === r ? "page" : undefined}
            >
              <span className="nav-icon">{["◷", "▦", "⌗", "≡"][i]}</span>
              {r === "history"
                ? "Time Machine"
                : r[0].toUpperCase() + r.slice(1)}
            </a>
          ))}
        </nav>
        <div className="future-nav">
          <span className="nav-label">LATER</span>
          {["Book", "Journal"].map((r) => (
            <button disabled key={r} aria-label={`${r} Planned`}>
              {r}
              <span>Planned</span>
            </button>
          ))}
        </div>
        <div className="sidebar-footer">
          <span className="status-dot" />
          Local workspace<small>Decision support · V1</small>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="topbar">
          <span>
            WORKSPACE <b>/</b> {route.toUpperCase()}
          </span>
          <span className="hypothesis">EXPERIMENTAL · UNCALIBRATED</span>
        </header>
        {health.data ? (
          <Context meta={health.data.meta} />
        ) : (
          <div className="context">
            <span>Checking snapshot mode and freshness…</span>
          </div>
        )}
        <main id="main-content" tabIndex={-1}>
          {health.isPending ? (
            <StatePanel title="Loading workstation">
              Checking the local snapshot. No research is available until
              validation completes.
            </StatePanel>
          ) : health.error ? (
            <ErrorPanel
              error={health.error}
              retry={() => void health.refetch()}
            />
          ) : !available ? (
            <StatePanel
              title={
                health.data?.meta.freshness === "STALE"
                  ? "Snapshot is stale"
                  : "Snapshot unavailable"
              }
              retry={() => void health.refetch()}
            >
              <p>Research content is blocked. Navigation remains available.</p>
              {health.data?.meta.reasons.map((r) => (
                <p key={r.code}>
                  {r.explanation} <code>{r.code}</code>
                </p>
              ))}
            </StatePanel>
          ) : (
            <>
              {route === "brief" && <Brief onSelect={setSelected} />}
              {route === "tape" && (
                <Tape
                  filters={filters}
                  onFilters={setFilters}
                  onSelect={setSelected}
                />
              )}
              {route === "sizer" && <Sizer initialSymbol={sizerSymbol} />}
              {route === "rules" && <Rules />}
              {route === "groups" && <Groups />}
              {route === "history" && (
                <History session={health.data?.meta.as_of_session ?? ""} />
              )}
            </>
          )}
        </main>
        <footer className="page-footer">
          Aperture · transparent evidence for discretionary review
          <span>
            {health.data?.meta.mode_label ?? "Snapshot mode unverified"}
          </span>
        </footer>
      </div>
      {selected && available && (
        <Detail
          symbol={selected}
          onClose={() => setSelected(null)}
          onSize={sizeSymbol}
        />
      )}
    </div>
  );
}
