import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../App";
// @ts-expect-error plain .mjs build script, no type declarations
import { parseCorrections as parse, render as renderLog } from "../../scripts/gen-corrections.mjs";
import corrections from "../generated/corrections.json";
import { CorrectionsView } from "./CorrectionsPage";

const parseCorrections = parse as (md: string) => { title: string; intro: string[]; rows: { date: string; wrong: string; fix: string }[] };

describe("Corrections log (REQ-WEB-FRESH.3)", () => {
  it("parses the table rows of docs/CORRECTIONS.md and skips the header and separator", () => {
    const md = "# Corrections log (public)\nIntro line.\n| Date | What was wrong | Fix |\n|---|---|---|\n| 2026-12-01 | Wrong pin | Moved it |\n| 2026-12-02 | Bad date | Fixed | extra |\n";
    expect(parseCorrections(md)).toEqual({
      title: "Corrections log (public)",
      intro: ["Intro line."],
      rows: [{ date: "2026-12-01", wrong: "Wrong pin", fix: "Moved it" }, { date: "2026-12-02", wrong: "Bad date", fix: "Fixed | extra" }],
    });
  });
  it("the generated file matches docs/CORRECTIONS.md (run npm run gen:corrections after editing the log)", () => {
    const generated = readFileSync(join(__dirname, "..", "generated", "corrections.json"), "utf8");
    expect(generated).toBe((renderLog as () => string)());
    expect(corrections.intro.length).toBeGreaterThan(0);
  });
  it("shows an empty state when there are no corrections, and a table when there are", () => {
    const { unmount } = render(<MemoryRouter><CorrectionsView log={{ title: "t", intro: ["Intro"], rows: [] }} /></MemoryRouter>);
    expect(screen.getByTestId("corrections-empty").textContent).toBe("No corrections yet.");
    unmount();
    render(<MemoryRouter><CorrectionsView log={{ title: "t", intro: [], rows: [{ date: "2026-12-01", wrong: "Wrong pin", fix: "Moved it" }] }} /></MemoryRouter>);
    expect(within(screen.getByTestId("corrections-table")).getByText("Wrong pin")).toBeTruthy();
  });
  it("is routed at /corrections and links to Report an error", () => {
    render(<MemoryRouter initialEntries={["/corrections"]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Corrections log" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Report an error" })).toBeTruthy();
  });
});
