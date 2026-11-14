import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
// @ts-expect-error plain .mjs build script, no type declarations
import { budgetVerdict, checkOrigins, findFetchRefs, findHosts, INERT_HOSTS } from "../../scripts/check-build.mjs";

type Files = [string, string][];
const check = checkOrigins as (files: Files) => string[];

describe("build origin check (REQ-WEB-PERF.2)", () => {
  it("passes same-origin markup", () => {
    const html = '<script type="module" src="/assets/index-abc.js"></script><link rel="stylesheet" href="/assets/index.css">';
    expect(check([["index.html", html]])).toEqual([]);
  });
  it("fails a script, stylesheet or image on another origin", () => {
    expect(check([["index.html", '<script src="https://cdn.example.com/x.js"></script>']]).length).toBeGreaterThan(0);
    expect(check([["index.html", '<link rel="stylesheet" href="//fonts.googleapis.com/css?family=Inter">']]).length).toBeGreaterThan(0);
    expect(check([["assets/a.css", "@font-face{src:url(https://fonts.gstatic.com/s/inter.woff2)}"]]).length).toBeGreaterThan(0);
    expect(check([["assets/a.css", '@import "https://x.example/a.css";']]).length).toBeGreaterThan(0);
  });
  it("fails an unreviewed host inside a script, and accepts a reviewed inert one", () => {
    expect(check([["assets/a.js", 'fetch("https://api.example.com/data")']])).toEqual(["assets/a.js: unreviewed host api.example.com"]);
    expect(check([["assets/a.js", 'const ns="http://www.w3.org/2000/svg"']])).toEqual([]);
  });
  it("finds hosts and fetch references", () => {
    expect([...(findHosts as (t: string) => Set<string>)('a "https://a.example/x" b http://b.example:8080/y')].sort()).toEqual(["a.example", "b.example"]);
    expect((findFetchRefs as (t: string, e: string) => string[])('<img src="https://x.example/i.png">', ".html")).toEqual(["https://x.example/i.png"]);
  });
  it("keeps a reason for every reviewed host", () => {
    for (const [host, why] of INERT_HOSTS as Map<string, string>) expect(why.length, host).toBeGreaterThan(5);
  });
});

describe("first-view budget gate (REQ-WEB-PERF.1)", () => {
  const verdict = budgetVerdict as (bytes: number, strict: boolean) => { over: boolean; fail: boolean };
  it("passes under 3 MB", () => {
    expect(verdict(3 * 1024 * 1024, true)).toEqual({ over: false, fail: false });
  });
  it("fails the build over 3 MB when strict, and only warns when not", () => {
    expect(verdict(3 * 1024 * 1024 + 1, true)).toEqual({ over: true, fail: true });
    expect(verdict(3 * 1024 * 1024 + 1, false)).toEqual({ over: true, fail: false });
  });
  it("the build script runs the strict budget check and writes the headers file (REQ-WEB-PERF.3)", () => {
    const pkg = JSON.parse(readFileSync(join(__dirname, "..", "..", "package.json"), "utf8")) as { scripts: Record<string, string> };
    expect(pkg.scripts.build).toContain("check-build.mjs --strict");
    expect(pkg.scripts.build).toContain("write-headers.ts");
  });
});
