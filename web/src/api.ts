import type { components } from "./api.generated";
export type Schemas = components["schemas"];
export type Meta = Schemas["ViewMetaV1"];
export type TapeRow = Schemas["TapeRowV1"];
export type Reason = Schemas["ReasonV1"];
export class ApiFailure extends Error {
  code: string;
  modeLabel?: string;
  constructor(message: string, code = "NETWORK_ERROR", modeLabel?: string) {
    super(message);
    this.code = code;
    this.modeLabel = modeLabel;
  }
}
export async function get<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    signal: AbortSignal.timeout(15000),
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      Schemas["ErrorV1"] | null;
    throw new ApiFailure(
      body?.message || "The local API is unavailable.",
      body?.code,
      body?.mode_label,
    );
  }
  return response.json() as Promise<T>;
}
