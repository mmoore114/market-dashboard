import type { Schemas } from "./api";
export type Group = Schemas["ResearchGroupV1"];
export type Row = Schemas["ResearchRowV1"];
export type Direction = "LONG" | "SHORT";
export const levels = [
  "SECTOR",
  "GROUP",
  "INDUSTRY",
  "SUB_INDUSTRY",
  "THEME",
] as const;
export const levelNames = [
  "Sectors",
  "Groups",
  "Industries",
  "Sub-industries",
  "Themes",
];
export function label(value: string | null | undefined) {
  return value?.replaceAll("_", " ").toLowerCase() ?? "Unavailable";
}
export function groupName(id: string) {
  try {
    const p: unknown = JSON.parse(id);
    if (Array.isArray(p)) return p.filter((v) => v != null).at(-1) as string;
  } catch {
    /* Retained plain identity. */
  }
  return id;
}
export const categoryNames: Record<string, string> = {
  STRATEGY: "Strategy",
  MISSING_DATA: "Missing evidence",
  INVALID_DATA: "Data issue",
  PROPOSAL: "Your proposal",
  LEGACY_SCOPE: "Retained decision issue",
};
