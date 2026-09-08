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
import type { Direction } from "./research";
const routes = ["brief", "groups", "tape", "sizer", "rules"] as const;
type Route = (typeof routes)[number] | "history";
function currentRoute(): Route {
  const r = window.location.hash.slice(1);
  return [...routes, "history"].includes(r) ? (r as Route) : "brief";
}
function preferences(): Filters {
  try {
    return {
      ...initialFilters,
      ...JSON.parse(sessionStorage.getItem("aperture-ui-v1") || "{}").filters,
    };
  } catch {
    return initialFilters;
  }
}
export function App() {
  const [route, setRoute] = useState<Route>(currentRoute);
  const [filters, setFilters] = useState(preferences);
  const [selected, setSelected] = useState<{
    symbol: string;
    direction: Direction;
  } | null>(null);
  const [sizer, setSizer] = useState<{ symbol: string; direction: Direction }>({
    symbol: "",
    direction: "LONG",
  });
  const [group, setGroup] = useState<{ id: string; kind: string } | null>(null);
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => get<Schemas["HealthV1"]>("/health"),
    refetchInterval: 30000,
  });
  const evidence = useQuery({
    queryKey: ["research-health"],
    queryFn: () =>
      get<Schemas["ResearchHealthV1"]>("/research/health", undefined, "v2"),
    enabled: health.data?.available === true,
  });
  useEffect(() => {
    const change = () => {
      setRoute(currentRoute());
      setSelected(null);
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    try {
      sessionStorage.setItem("aperture-ui-v1", JSON.stringify({ filters }));
    } catch {
      /* Optional preferences. */
    }
  }, [filters]);
  const navigate = (r: Route) => {
    setSelected(null);
    setRoute(r);
    window.location.hash = r;
  };
  const openTape = (action: string) => {
    setFilters({ ...initialFilters, action });
    navigate("tape");
  };
  const openGroup = (id: string, kind = "INDUSTRY") => {
    setGroup({ id, kind });
    navigate("groups");
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
          {routes.map((r) => (
            <a
              key={r}
              href={"#" + r}
              aria-current={route === r ? "page" : undefined}
            >
              {r[0].toUpperCase() + r.slice(1)}
            </a>
          ))}
        </nav>
        <details className="future-nav">
          <summary>Planned tools</summary>
          <a href="#history">Time Machine</a>
          <p>Book · Journal</p>
        </details>
        <div className="sidebar-footer">
          Local research<small>Discretionary decisions · no orders</small>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="topbar">
          <span>RESEARCH / {route.toUpperCase()}</span>
          <span className="hypothesis">EXPERIMENTAL · UNCALIBRATED</span>
        </header>
        {health.data && (
          <Context meta={health.data.meta} missing={evidence.data?.missing} />
        )}
        <main id="main-content" tabIndex={-1}>
          {health.isPending ? (
            <StatePanel title="Loading workstation">
              Validating local evidence…
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
            >
              <p>
                Research is unavailable until a current verified snapshot is
                supplied. The retained deadline is unchanged.
              </p>
            </StatePanel>
          ) : (
            <>
              {route === "brief" && (
                <Brief
                  onSelect={(symbol, direction = "LONG") =>
                    setSelected({ symbol, direction })
                  }
                  onTape={openTape}
                  onGroup={openGroup}
                />
              )}
              <div hidden={route !== "tape"}>
                {/* Preserve list DOM, filters and scroll across detail/sizing. */}
                <Tape
                  filters={filters}
                  onFilters={setFilters}
                  onSelect={(symbol, direction = "LONG") =>
                    setSelected({ symbol, direction })
                  }
                  onGroup={openGroup}
                  enabled={route === "tape"}
                />
              </div>
              <div hidden={route !== "groups"}>
                <Groups
                  onSelect={(symbol, direction = "LONG") =>
                    setSelected({ symbol, direction })
                  }
                  onTape={(id) => {
                    setFilters({ ...initialFilters, group: id });
                    navigate("tape");
                  }}
                  initialGroup={group}
                  enabled={route === "groups"}
                />
              </div>
              {route === "sizer" && (
                <Sizer
                  key={sizer.symbol + "|" + sizer.direction}
                  initialSymbol={sizer.symbol}
                  initialDirection={sizer.direction}
                />
              )}
              {route === "rules" && <Rules />}
              {route === "history" && <History />}
            </>
          )}
        </main>
        <footer className="page-footer">
          Aperture · evidence for discretionary review
          <span>{health.data?.meta.mode_label}</span>
        </footer>
      </div>
      {selected && available && (
        <Detail
          symbol={selected.symbol}
          initialDirection={selected.direction}
          onClose={() => setSelected(null)}
          onSize={(symbol, direction) => {
            setSizer({ symbol, direction });
            navigate("sizer");
          }}
        />
      )}
    </div>
  );
}
