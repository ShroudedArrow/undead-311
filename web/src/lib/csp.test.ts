import { describe, expect, it } from "vitest";
import { CSP_DIRECTIVES, cspString, headersFile } from "./csp";

describe("Content Security Policy (REQ-WEB-PERF.3, REQ-OPS-HOST.3)", () => {
  const csp = cspString();
  it("allows only same-origin sources: no host, scheme wildcard or *", () => {
    expect(csp).not.toMatch(/https?:|\/\/|\*|wss?:/);
  });
  it("never allows inline or eval scripts", () => {
    expect(CSP_DIRECTIVES["script-src"]).toEqual(["'self'"]);
    expect(csp).not.toContain("unsafe-eval");
  });
  it("covers scripts, styles, images, fonts and connections", () => {
    for (const d of ["default-src", "script-src", "style-src", "img-src", "font-src", "connect-src"]) expect(CSP_DIRECTIVES[d]).toContain("'self'");
    expect(CSP_DIRECTIVES["object-src"]).toEqual(["'none'"]);
    expect(CSP_DIRECTIVES["frame-ancestors"]).toEqual(["'none'"]);
  });
  it("renders a Netlify _headers file for every path", () => {
    const f = headersFile();
    expect(f.startsWith("/*\n")).toBe(true);
    expect(f).toContain(`  Content-Security-Policy: ${csp}\n`);
    expect(f).toContain("X-Content-Type-Options: nosniff");
  });
});
