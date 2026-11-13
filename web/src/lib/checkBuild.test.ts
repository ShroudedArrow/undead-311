import { describe, expect, it } from "vitest";
// @ts-expect-error plain .mjs build script, no type declarations
import { checkOrigins, findFetchRefs, findHosts, INERT_HOSTS } from "../../scripts/check-build.mjs";

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
