import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";

// The real map needs WebGL; the page's contract is the rows it hands to the map.
const mapRows = vi.fn();
const mapLabels = vi.fn();
vi.mock("../map/MapView", () => ({
  default: (props: { rows: { id: string }[]; bulkIds?: ReadonlySet<string> | null; labels?: { name: string }[] }) => {
    mapRows(props.rows.map((r) => r.id));
    mapLabels((props.labels ?? []).map((l) => l.name));
    return <div data-testid="map" data-marker-count={props.rows.length} data-bulk-ids={props.bulkIds ? [...props.bulkIds].sort().join(",") : ""} />;
  },
}));

const POINTS = {
  data_version: "v", n: 4,
  id: ["a", "b", "c", "d"], lat: [42.3, 42.31, 42.32, 42.33], lon: [-71.1, -71.1, -71.1, -71.1],
  tier: ["headline", "headline", "headline", "sensitivity"], family: ["sign", "sign", "sidewalk", "sign"],
  department: ["PWDx", "BTDT", null, "PWDx"], neighborhood: ["Dorchester", "Roxbury", "Roxbury", "Roxbury"], year: [2020, 2021, 2021, 2021],
};

function stubFetch(bulkFlags: [boolean, boolean, boolean, boolean] = [false, true, true, false]) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const zz = (id: string, bulk: boolean) => ({ zombie_id: id, incident_id: `I-${id}`, resurrection_id: `R-${id}`, reports_after: 1, gap_days: 3, match_mode: "radius", distance_m: 5, tier: "headline", baseline_p: 0.1, confidence: 0.8, confidence_partial: false, is_planned_followup: false, after_temporary_fix: false, source_unknown: false, city_rereport: false, chain_id: `C-${id}`, times_risen: 1, skeptic_verdict: "survives", skeptic_notes: "", type_family: "sign", department: null, neighborhood: "Roxbury", coroner_label: "resolved", bulk_closure: bulk, close_year: 2020, resurrection_date: "2021-01-01" });
    const body = String(url).endsWith("zombies.json") ? { data_version: "v", zombies: [zz("a", bulkFlags[0]), zz("b", bulkFlags[1]), zz("c", bulkFlags[2]), zz("d", bulkFlags[3])] } : String(url).endsWith("points.json") ? POINTS : { data_version: "v", last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" };
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
}

afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); mapRows.mockClear(); mapLabels.mockClear(); });

describe("HomePage (REQ-WEB-MAP.2-4)", () => {
  it("shows headline zombies only by default, and the count matches the map set", async () => {
    stubFetch();
    render(<MemoryRouter><App /></MemoryRouter>);
    expect(await screen.findByText("3 possible zombies match these filters")).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("map").getAttribute("data-marker-count")).toBe("3"));
    expect(mapRows).toHaveBeenLastCalledWith(["a", "b", "c"]);
  });

  it("filters by neighborhood and updates the count and the map together", async () => {
    stubFetch();
    const user = userEvent.setup();
    render(<MemoryRouter><App /></MemoryRouter>);
    await screen.findByText("3 possible zombies match these filters");
    await user.click(screen.getByText("Neighborhood"));
    await user.click(within(screen.getByRole("form", { name: "Filters" })).getByLabelText(/Roxbury/));
    expect(await screen.findByText("2 possible zombies match these filters")).toBeTruthy();
    expect(mapRows).toHaveBeenLastCalledWith(["b", "c"]);
  });

  it("hands the map neighborhood names from every point, so filtering does not move or drop them (ops#18)", async () => {
    stubFetch();
    const user = userEvent.setup();
    render(<MemoryRouter><App /></MemoryRouter>);
    await screen.findByText("3 possible zombies match these filters");
    expect(mapLabels).toHaveBeenLastCalledWith(["Roxbury"]);
    await user.click(screen.getByText("Neighborhood"));
    await user.click(within(screen.getByRole("form", { name: "Filters" })).getByLabelText(/Dorchester/));
    expect(await screen.findByText("1 possible zombie matches these filters")).toBeTruthy();
    expect(mapLabels).toHaveBeenLastCalledWith(["Roxbury"]);
  });

  it("puts the filters behind a Show filters button that reports its state (UX-7)", async () => {
    stubFetch();
    const user = userEvent.setup();
    render(<MemoryRouter><App /></MemoryRouter>);
    const toggle = await screen.findByRole("button", { name: "Show filters" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    await user.click(toggle);
    expect(screen.getByRole("button", { name: "Hide filters" }).getAttribute("aria-expanded")).toBe("true");
  });

  it("names departments in words, with the code in parentheses (UX-8)", async () => {
    stubFetch();
    const user = userEvent.setup();
    render(<MemoryRouter><App /></MemoryRouter>);
    await screen.findByText("3 possible zombies match these filters");
    await user.click(screen.getByText("Department"));
    expect(screen.getByText(/Public Works Department \(PWDx\)/)).toBeTruthy();
    expect(screen.getByText(/Boston Transportation Department \(BTDT\)/)).toBeTruthy();
  });

  it("shows an error state for the points panel but keeps the page (REQ-WEB-DATA.2)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response));
    render(<MemoryRouter><App /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("Independent project. Not affiliated with the City of Boston.")).toBeTruthy();
  });
});

describe("Sensitivity tier toggle (REQ-WEB-TIER.1-2)", () => {
  it("is off by default: no all-tier count, and the map has only headline rows", async () => {
    stubFetch();
    render(<MemoryRouter><App /></MemoryRouter>);
    await screen.findByText("3 possible zombies match these filters");
    expect((screen.getByLabelText("Include cases outside the headline count") as HTMLInputElement).checked).toBe(false);
    expect(screen.queryByTestId("count-all")).toBeNull();
    expect(mapRows).toHaveBeenLastCalledWith(["a", "b", "c"]);
  });
  it("adds the other tiers to the map and shows the headline count first, then the all-tier count", async () => {
    stubFetch();
    const user = userEvent.setup();
    render(<MemoryRouter><App /></MemoryRouter>);
    await screen.findByText("3 possible zombies match these filters");
    await user.click(screen.getByLabelText("Include cases outside the headline count"));
    expect(await screen.findByTestId("count-all")).toBeTruthy();
    expect(screen.getByTestId("count").textContent).toBe("3 possible zombies match these filters");
    expect(screen.getByTestId("count-all").textContent).toBe("4 when cases outside the headline are included");
    const [first, second] = [screen.getByTestId("count"), screen.getByTestId("count-all")];
    expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(mapRows).toHaveBeenLastCalledWith(["a", "b", "c", "d"]);
  });
  it("the table labels which tier counts each row, in words", async () => {
    stubFetch();
    render(<MemoryRouter initialEntries={["/?view=table&tier=all"]}><App /></MemoryRouter>);
    const table = await screen.findByTestId("zombie-table");
    expect(within(within(table).getAllByRole("row").find((r) => r.getAttribute("data-id") === "d") as HTMLElement).getByText("Sensitivity check")).toBeTruthy();
  });
});

describe("Bulk-closure layer (REQ-WEB-DEATHS.1)", () => {
  it("is off by default: no zombie file is requested and nothing is ringed", async () => {
    stubFetch();
    render(<MemoryRouter><App /></MemoryRouter>);
    await screen.findByText("3 possible zombies match these filters");
    expect(screen.getByTestId("map").getAttribute("data-bulk-ids")).toBe("");
    expect((vi.mocked(fetch).mock.calls as unknown[][]).some((c) => String(c[0]).endsWith("zombies.json"))).toBe(false);
  });
  it("rings only the visible zombies whose closure was part of a bulk closure, and says how many", async () => {
    stubFetch();
    const user = userEvent.setup();
    render(<MemoryRouter><App /></MemoryRouter>);
    await screen.findByText("3 possible zombies match these filters");
    await user.click(screen.getByLabelText("Mark closures that were part of a bulk closure"));
    expect(await screen.findByText("2 of the possible zombies shown follow a bulk closure, ringed in orange.")).toBeTruthy();
    expect(screen.getByTestId("map").getAttribute("data-bulk-ids")).toBe("b,c");
  });
  it("says so when no zombie shown follows a bulk closure, instead of '0 ... ringed in orange' (REQ-WEB-DEATHS.1; UX-28)", async () => {
    stubFetch([false, false, false, false]);
    const user = userEvent.setup();
    render(<MemoryRouter><App /></MemoryRouter>);
    await screen.findByText("3 possible zombies match these filters");
    await user.click(screen.getByLabelText("Mark closures that were part of a bulk closure"));
    expect(await screen.findByText("None of the possible zombies shown follow a bulk closure, so no rings are drawn.")).toBeTruthy();
    expect(screen.queryByText(/^0 of the possible zombies/)).toBeNull();
  });
  it("adds a Bulk closure column to the table that mirrors the map", async () => {
    stubFetch();
    render(<MemoryRouter initialEntries={["/?view=table&bulk=1"]}><App /></MemoryRouter>);
    const table = await screen.findByTestId("zombie-table");
    const rowB = within(table).getAllByRole("row").find((r) => r.getAttribute("data-id") === "b") as HTMLElement;
    expect(within(table).getByRole("columnheader", { name: "Bulk closure" })).toBeTruthy();
    expect(await within(table).findAllByText("Part of a bulk closure")).toHaveLength(2);
    expect(rowB.textContent).toContain("Part of a bulk closure");
  });
});

describe("Table view mirrors the map (REQ-WEB-TABLE.1)", () => {
  it("lists the same zombies the map got, and each row links to its card", async () => {
    stubFetch();
    render(<MemoryRouter initialEntries={["/?view=table&n=Roxbury"]}><App /></MemoryRouter>);
    await screen.findByText("2 possible zombies match these filters");
    const table = await screen.findByTestId("zombie-table");
    const ids = within(table).getAllByRole("row").slice(1).map((r) => r.getAttribute("data-id"));
    expect(ids.sort()).toEqual(["b", "c"]);
    expect(within(table).getByRole("link", { name: "Open card b" }).getAttribute("href")).toBe("/zombie/b?view=table&n=Roxbury");
  });
  it("sorts when a header is pressed and marks aria-sort", async () => {
    stubFetch();
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/?view=table"]}><App /></MemoryRouter>);
    const table = await screen.findByTestId("zombie-table");
    const header = within(table).getByRole("columnheader", { name: /Neighborhood/ });
    await user.click(within(header).getByRole("button"));
    expect(header.getAttribute("aria-sort")).toBe("ascending");
    await user.click(within(header).getByRole("button"));
    expect(header.getAttribute("aria-sort")).toBe("descending");
  });
});
