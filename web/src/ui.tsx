import type { ReactNode } from "react";
import { ApiFailure, type Reason, type Meta } from "./api";

export function number(value: number | null | undefined, digits = 1) {
  return value == null
    ? "Unknown"
    : value.toLocaleString("en-US", { maximumFractionDigits: digits });
}
export function money(value: number | null | undefined) {
  return value == null
    ? "Unknown"
    : `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
export function Chip({ value }: { value: string | null | undefined }) {
  const label = value ?? "UNKNOWN";
  const tone = [
    "GREEN",
    "ACT",
    "CLEAR",
    "VALID",
    "UPTREND",
    "NOT_LAGGING",
    "PASS",
  ].includes(label)
    ? "positive"
    : ["RED", "BLOCKED", "INVALID", "FAILED", "FAIL", "LAGGING"].includes(label)
      ? "negative"
      : ["YELLOW", "WATCH", "TRADE", "NEAR_TRIGGER", "EMERGING"].includes(label)
        ? "caution"
        : "neutral";
  return <span className={`chip ${tone}`}>{label.replaceAll("_", " ")}</span>;
}
export function Reasons({ reasons }: { reasons: readonly Reason[] }) {
  return (
    <ul className="reason-list">
      {reasons.map((r, i) => (
        <li key={`${r.code}-${i}`}>
          <span>{r.explanation}</span>
          <code>{r.code}</code>
        </li>
      ))}
    </ul>
  );
}
export function StatePanel({
  title,
  children,
  retry,
}: {
  title: string;
  children?: ReactNode;
  retry?: () => void;
}) {
  return (
    <div className="state-panel" role="status">
      <span className="state-symbol">◈</span>
      <h2>{title}</h2>
      <div>{children}</div>
      {retry && <button onClick={retry}>Try again</button>}
    </div>
  );
}
export function ErrorPanel({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) {
  return (
    <StatePanel title="Research unavailable" retry={retry}>
      <p>{error.message || "The local API could not be reached."}</p>
      {error instanceof ApiFailure && (
        <>
          <code>{error.code}</code>
          <p>{error.modeLabel}</p>
        </>
      )}
    </StatePanel>
  );
}
export function PageTitle({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-title">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
      </div>
      {children}
    </header>
  );
}
export function Context({ meta }: { meta: Meta }) {
  return (
    <div className="context">
      <span>{meta.mode_label}</span>
      <span>
        As of <b>{meta.as_of_session ?? "Unavailable"}</b>
      </span>
      <span>
        Action session <b>{meta.action_session ?? "Unavailable"}</b>
      </span>
      <span>
        Freshness <b>{meta.freshness}</b>
      </span>
    </div>
  );
}
export function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
