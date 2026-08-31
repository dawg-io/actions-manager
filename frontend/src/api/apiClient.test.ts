import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

const SRC = join(__dirname, "..");

// apiClient.ts legitimately calls axios.create, and the manual mock exists to
// stand in for the library. Tests mock it by design.
const ALLOWED = new Set(["api/apiClient.ts", "__mocks__/axios.ts"]);

const isCheckable = (rel: string) =>
  /\.(ts|tsx)$/.test(rel) && !rel.includes(".test.") && !ALLOWED.has(rel);

const walk = (dir: string): string[] =>
  readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });

// Only apiClient sets withCredentials, and WriteProtectionMiddleware
// (backend/main.py) authenticates every /api/* request, reads included. A bare
// axios call therefore arrives with no session cookie whenever the API is on a
// different origin than the app - which is how the cloud deployment is
// configured - and comes back 401.
//
// This has now shipped three times: the project deletion summary, then
// environments/secrets/workflows/projects, then RulesetManager. The third got
// through because this guard only walked src/api - and RulesetManager calls
// the API straight from the component. It walks all of src now: where the call
// lives has nothing to do with whether it needs the session.
describe("no module issues bare axios requests", () => {
  const files = walk(SRC)
    .map((f) => relative(SRC, f).replaceAll(/[\\/]/g, "/"))
    .filter(isCheckable);

  it("finds the modules to check", () => {
    expect(files.length).toBeGreaterThan(100);
  });

  it.each(files)("%s", (rel) => {
    const source = readFileSync(join(SRC, rel), "utf8");
    const bareCalls = source.match(/\baxios\.(get|post|put|patch|delete|request)\s*\(/g);

    expect(bareCalls).toBeNull();
  });
});
