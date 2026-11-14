import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";

// The real map needs WebGL; the page's contract is the rows it hands to the map.
const mapRows = vi.fn();
vi.mock("../map/MapView", () => ({
  default: (props: { rows: { id: string }[] }) => {
    mapRows(props.rows.map((r) => r.id));
    return <div data-testid="map" data-marker-count={props.rows.length} />;
  },
}));

const POINTS = {
  data_version: "v", n: 4,
  id: ["a", "b", "c", "d"], lat: [42.3, 42.31, 42.32, 42.33], lon: [-71.1, -71.1, -71.1, -71.1],
  tier: ["headline", "headline", "headline", "sensitivity"], family: ["sign", "sign", "sidewalk", "sign"],
  department: ["PWDx", "BTDT", null, "PWDx"], neighborhood: ["Dorchester", "Roxbury", "Roxbury", "Roxbury"], year: [2020, 2021, 2021, 2021],
};

function stubFetch() {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const body = String(url).endsWith("points.json") ? POINTS : { data_version: "v", last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" };
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
}

afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); mapRows.mockClear(); });

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
