import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";
import { AutopsyCard, type CardWithPartial } from "./AutopsyCard";

vi.mock("../map/MapView", () => ({ default: () => <div data-testid="map" /> }));

const CARD: CardWithPartial = {
  zombie_id: "I-1:2",
  original: { id: "101001", system: "legacy", open_time: "2026-01-10T15:00:00Z", close_time: "2026-01-12T15:00:00Z", type_raw: "Request for Pothole Repair", status: "Closed", closure_text: "Case Closed Case Resolved patched", street: "Dorchester Ave", lat: 42.3, lon: -71.05 },
  rereport: { id: "BCS-2", system: "new", open_time: "2026-01-20T15:00:00Z", close_time: null, type_raw: "Pothole", status: "Open", closure_text: null, street: "Dorchester Ave", lat: 42.3, lon: -71.05 },
  cause_of_death: "made_safe_temporary",
  gap_days: 8.04,
  resurrection_date: "2026-01-20",
  confidence: 0.724,
  tier: "headline",
  skeptic_verdict: "weakened",
  skeptic_notes: "The closure text names a different block.",
  reports_after: 3,
  times_risen: 1,
  bulk_closure: true,
  confidence_partial: true,
};

describe("AutopsyCard content (REQ-WEB-CARD.1, .3, .6)", () => {
  it("shows cause of death, time in the grave, resurrection date, confidence, Skeptic and both cases", () => {
    render(<AutopsyCard card={CARD} />);
    const card = screen.getByTestId("autopsy-card");
    expect(within(card).getByText("Cause of death")).toBeTruthy();
    expect(within(card).getByText("Made safe for now")).toBeTruthy();
    expect(within(card).getByText("8 days")).toBeTruthy();
    expect(within(card).getByText("Jan 20, 2026")).toBeTruthy();
    expect(within(card).getByText(/72 of 100/)).toBeTruthy();
    expect(within(card).getByText("The closure text names a different block.")).toBeTruthy();
    expect(within(card).getByText(/The evidence is weaker/)).toBeTruthy();
    expect(within(card).getByText("Original case")).toBeTruthy();
    expect(within(card).getByText("Reported again")).toBeTruthy();
    expect(within(card).getByText("No closure text recorded.")).toBeTruthy();
    expect(within(card).getByText("Not closed")).toBeTruthy();
  });
  it("says a free-text note is not shown when the pipeline withheld it, and keeps the empty-note text for no note (REQ-ING-PII.5)", () => {
    const hidden = { ...CARD, original: { ...CARD.original, closure_text: null, closure_text_hidden: true } };
    render(<AutopsyCard card={hidden} />);
    const card = screen.getByTestId("autopsy-card");
    expect(within(card).getByText("Free-text note not shown")).toBeTruthy();
    expect(within(card).getAllByText("No closure text recorded.")).toHaveLength(1); // only the re-report, which has no note
  });
  it("shows hours, not 0 days, for a re-report within a day (UX-9)", () => {
    render(<AutopsyCard card={{ ...CARD, gap_days: 4 / 24 }} />);
    const card = screen.getByTestId("autopsy-card");
    expect(within(card).getByText("4 hours")).toBeTruthy();
    expect(within(card).queryByText(/^0 days?$/)).toBeNull();
  });
  it("links an earlier-system case ID to the city's page and shows a new-system ID as text, because that link is not verified (REQ-WEB-CARD.1, ops#13)", () => {
    render(<AutopsyCard card={CARD} />);
    const link = screen.getByRole("link", { name: "View case 101001 on the city's site" });
    expect(link.getAttribute("href")).toBe("https://311.boston.gov/reports/101001");
    expect(screen.queryByRole("link", { name: /View case BCS-2/ })).toBeNull();
    expect(screen.getByText("BCS-2")).toBeTruthy();
  });
  it("notes partial confidence only when flagged", () => {
    const { rerender } = render(<AutopsyCard card={CARD} />);
    expect(screen.getByText(/Partial:/)).toBeTruthy();
    rerender(<AutopsyCard card={{ ...CARD, confidence_partial: false }} />);
    expect(screen.queryByText(/Partial:/)).toBeNull();
  });
  it("warns about a bulk closure with text, not color alone", () => {
    const { rerender } = render(<AutopsyCard card={CARD} />);
    expect(screen.getByTestId("bulk-warning").textContent).toMatch(/^Bulk closure:/);
    rerender(<AutopsyCard card={{ ...CARD, bulk_closure: false }} />);
    expect(screen.queryByTestId("bulk-warning")).toBeNull();
  });
  it("labels non-headline tiers on the card (REQ-WEB-TIER.1 note)", () => {
    render(<AutopsyCard card={{ ...CARD, tier: "source_unknown" }} />);
    expect(screen.getByText(/Outside the headline count/)).toBeTruthy();
  });
  it("says 'possible zombie', never claims intent or names a worker (REQ-WEB-CARD.3)", () => {
    render(<AutopsyCard card={CARD} />);
    const text = screen.getByTestId("autopsy-card").textContent ?? "";
    expect(text).toMatch(/possible zombie/i);
    expect(text).not.toMatch(/lied|fake|worker|employee|negligen/i);
  });
  it("shows the CLOSED stamp struck through and the REPORTED AGAIN stamp", () => {
    render(<AutopsyCard card={CARD} />);
    expect(screen.getByText("CLOSED").className).toContain("stamp-closed");
    expect(screen.getByText("REPORTED AGAIN").className).toContain("stamp-again");
  });
  it("writes the case system without nested parentheses and explains why a current-system ID has no link (REQ-WEB-CARD.1; ops#118, ops#119)", () => {
    render(<AutopsyCard card={CARD} />);
    const [orig, again] = [screen.getByRole("region", { name: "Original case" }), screen.getByRole("region", { name: "Reported again" })];
    const line = (el: HTMLElement) => el.querySelector("dd")?.textContent ?? "";
    expect(line(orig)).toContain("101001 (Earlier 311 system)");
    expect(within(orig).queryByTestId("new-case-note")).toBeNull();
    expect(within(orig).getByRole("link", { name: /101001/ })).toBeTruthy();
    expect(line(again)).toContain("BCS-2 (Current 311 system, from August 2025)");
    expect(line(again)).not.toMatch(/\([^)]*\([^)]*\)/);
    expect(within(again).queryByRole("link")).toBeNull();
    const note = within(again).getByTestId("new-case-note");
    expect(note.textContent).toMatch(/not linked yet.*Search this case number/);
    // UX-35: the note is its own block under the case number, not an inline run-on.
    expect(note.tagName).toBe("P");
    expect(note.closest("span")).toBeNull();
  });
});

describe("AutopsyCard as a mock postmortem report (REQ-WEB-CARD.1-3, design review 13)", () => {
  const MANY = "First objection here. Second objection here. Third objection here. Fourth objection here.";
  it("heads the form with the fictional report title, the re-report's case number and the page line, and names no agency", () => {
    render(<AutopsyCard card={CARD} />);
    const card = screen.getByTestId("autopsy-card");
    expect(within(card).getByText("Undead 311, report of postmortem examination")).toBeTruthy();
    expect(within(card).getByText("Case no. BCS-2")).toBeTruthy();
    expect(within(card).getByText("Page 1 of 1")).toBeTruthy();
    expect(card.textContent).not.toMatch(/City of Boston|seal|department of/i);
  });
  it("labels the fields and keeps each value a plain fact", () => {
    render(<AutopsyCard card={CARD} />);
    const card = screen.getByTestId("autopsy-card");
    const field = (label: string) => within(card).getByText(label).parentElement as HTMLElement;
    expect(field("Decedent").textContent).toContain("Request for Pothole Repair, Dorchester Ave");
    expect(field("Date of death (closed as fixed)").textContent).toContain("Jan 12, 2026");
    expect(field("Date of resurrection (reported again)").textContent).toContain("Jan 20, 2026");
    expect(field("Time in the grave").textContent).toContain("8 days");
    expect(field("Cause of death").textContent).toContain("Made safe for now");
  });
  it("states the findings: case types, and the distance between the two reports", () => {
    const far = { ...CARD, rereport: { ...CARD.rereport, lat: 42.3003, lon: -71.05 } };
    render(<AutopsyCard card={far} />);
    const findings = screen.getByTestId("findings").textContent ?? "";
    expect(findings).toContain("Different case types: Request for Pothole Repair and Pothole.");
    expect(findings).toMatch(/The two reports are 33 m apart\./);
  });
  it("says the two reports sit at the same point when they share coordinates, and draws the sketch with a text alternative", () => {
    render(<AutopsyCard card={CARD} />);
    expect(screen.getByTestId("findings").textContent).toContain("The two reports sit at the same point.");
    const svg = within(screen.getByTestId("location-diagram")).getByRole("img");
    expect(svg.getAttribute("aria-label")).toBe("Sketch of the two reports on Dorchester Ave: the first report and the report after the closure, 0 m apart.");
    expect(within(screen.getByTestId("location-diagram")).getByText("Dorchester Ave. Sketch, not to scale.")).toBeTruthy();
  });
  it("draws overlapping markers and no distance line for a same-point pair, and the full distance line otherwise (review follow-up)", () => {
    const { container, rerender } = render(<AutopsyCard card={CARD} />);
    expect(container.querySelectorAll(".diagram-dimension")).toHaveLength(0);
    rerender(<AutopsyCard card={{ ...CARD, rereport: { ...CARD.rereport, lat: 42.3003, lon: -71.05 } }} />);
    expect(container.querySelectorAll(".diagram-dimension")).toHaveLength(3);
  });
  it("shows the top two objections under 'Why this might not be a zombie', the rest behind Show more, with a Skeptic byline", async () => {
    const user = userEvent.setup();
    render(<AutopsyCard card={{ ...CARD, skeptic_notes: MANY }} />);
    const card = screen.getByTestId("autopsy-card");
    expect(within(card).getByText("Second opinion")).toBeTruthy();
    expect(within(card).getByText("Why this might not be a zombie")).toBeTruthy();
    expect(within(card).getByText("Skeptic")).toBeTruthy();
    expect(within(card).getAllByRole("listitem").filter((li) => /objection here/.test(li.textContent ?? ""))).toHaveLength(2);
    const more = within(card).getByRole("button", { name: "Show 2 more" });
    expect(more.getAttribute("aria-expanded")).toBe("false");
    await user.click(more);
    expect(within(card).getAllByRole("listitem").filter((li) => /objection here/.test(li.textContent ?? ""))).toHaveLength(4);
    expect(within(card).getByRole("button", { name: "Show fewer" }).getAttribute("aria-expanded")).toBe("true");
  });
  it("offers no Show more for two objections or fewer", () => {
    render(<AutopsyCard card={CARD} />);
    expect(screen.queryByRole("button", { name: /Show .* more/ })).toBeNull();
  });
  it("signs the form as the Coroner (automated)", () => {
    render(<AutopsyCard card={CARD} />);
    expect(screen.getByText("Examined by: the Coroner (automated)")).toBeTruthy();
  });
  it("stamps POSSIBLE on an ordinary card and RECORD-CONFIRMED only when asked, with the status readable as text", () => {
    const { rerender } = render(<AutopsyCard card={CARD} />);
    expect(screen.getByTestId("verdict-stamp").textContent).toBe("Status: POSSIBLE");
    rerender(<AutopsyCard card={CARD} recordConfirmed />);
    expect(screen.getByTestId("verdict-stamp").textContent).toBe("Status: RECORD-CONFIRMED");
  });
});

describe("AutopsyCard styling (REQ-WEB-CARD.2, .5, .6)", () => {
  const css = readFileSync(join(__dirname, "..", "styles", "app.css"), "utf8");
  it("uses the typewriter face only inside the form", () => {
    const rules = css.split("}").map((r) => r.trim()).filter((r) => r.includes("--font-form") || /courier/i.test(r));
    expect(rules.length).toBeGreaterThan(0);
    for (const r of rules) expect(r.split("{")[0]).toMatch(/\.autopsy-form/);
  });
  it("collapses to one copy in a bottom sheet under 640 px", () => {
    const phone = css.slice(css.indexOf("@media (max-width: 640px)", css.indexOf("Autopsy card")));
    expect(phone).toMatch(/\.card-host[^}]*position: fixed/);
    expect(phone).toMatch(/\.autopsy::before, \.autopsy::after \{ display: none/);
  });
  it("never sets text in pink or orange (REQ-WEB-A11Y.1)", () => {
    for (const rule of css.split("}")) {
      const body = rule.split("{")[1] ?? "";
      expect(body).not.toMatch(/(^|[;\s])color:\s*var\(--(survey-pink|cone-orange)\)/);
    }
  });
});

describe("CardRoute loads lazily (REQ-WEB-CARD.4)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    clearDataCache();
  });
  it("fetches only the points file and the one shard the card lives in", async () => {
    const points = { data_version: "v", n: 1, id: ["I-1:2"], lat: [42.3], lon: [-71.05], tier: ["headline"], family: ["pothole_roadway"], department: ["PWDx"], neighborhood: ["Dorchester"], year: [2026] };
    const shard = { data_version: "v", shard: "dorchester-2026", cards: [CARD] };
    const fetchMock = vi.fn(async (url: string) => {
      const u = String(url);
      const body = u.endsWith("points.json") ? points : u.includes("cards/") ? shard : { data_version: "v", last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" };
      return { ok: true, status: 200, json: async () => body } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter initialEntries={["/zombie/I-1%3A2"]}><App /></MemoryRouter>);
    expect(await screen.findByTestId("autopsy-card")).toBeTruthy();
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls.filter((u) => u.includes("cards/"))).toEqual(["/data/cards/dorchester-2026.json"]);
    expect(urls.some((u) => u.endsWith("zombies.json"))).toBe(false);
    expect(screen.getByRole("dialog", { name: "Autopsy report" })).toBeTruthy();
  });
  it("shows a not-found message for an unknown id", async () => {
    const points = { data_version: "v", n: 0, id: [], lat: [], lon: [], tier: [], family: [], department: [], neighborhood: [], year: [] };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, status: 200, json: async () => (String(url).endsWith("points.json") ? points : { data_version: "v", last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" }) }) as Response));
    render(<MemoryRouter initialEntries={["/zombie/nope"]}><App /></MemoryRouter>);
    expect(await screen.findByText(/No card was found for nope/)).toBeTruthy();
  });
});

describe("Report an error on every card (REQ-WEB-FRESH.3)", () => {
  it("links to the public issue form with the zombie ID in the title", () => {
    render(<MemoryRouter><AutopsyCard card={CARD} /></MemoryRouter>);
    const link = screen.getByRole("link", { name: "Report an error" });
    expect(link.getAttribute("href")).toContain("/issues/new?title=Error%20report%3A%20I-1%3A2");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });
});
