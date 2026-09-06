import { readFile } from "node:fs/promises";
import { format } from "prettier";
import openapiTS, { astToString } from "openapi-typescript";
const ast = await openapiTS(new URL("../../api/openapi.json", import.meta.url));
const generated = await format(astToString(ast), { parser: "typescript" });
const existing = await readFile(
  new URL("../src/api.generated.ts", import.meta.url),
  "utf8",
);
// Ignore the generator's standard banner, never ignore schema/type differences.
const normalize = (s) => s.replace(/^\/\*\*[\s\S]*?\*\/\s*/, "").trim();
if (normalize(existing) !== normalize(generated)) {
  console.error("API type drift. Run npm run generate:api.");
  process.exit(1);
}
console.log("Frontend types match the committed OpenAPI contract.");
