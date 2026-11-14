import { describe, expect, it } from "vitest";
import { canonicalDepartment, departmentLabel, groupLabel } from "./labels";
import { pointsToRows } from "./points";
import { visibleSet } from "./filter";
import type { PointsFile } from "./parse";

describe("one filter key per department across both systems (REQ-WEB-MAP.2, UX-11)", () => {
  it("maps new-system names to the legacy code and leaves codes and unknown values alone", () => {
    expect(canonicalDepartment("Public Works Department (PWD)")).toBe("PWDx");
    expect(canonicalDepartment("Boston Transportation Department (BTD)")).toBe("BTDT");
    expect(canonicalDepartment("PWDx")).toBe("PWDx");
    expect(canonicalDepartment("Some Other Office")).toBe("Some Other Office");
    expect(canonicalDepartment(null)).toBeNull();
  });

  it("gives INFO a readable label instead of the bare code", () => {
    expect(departmentLabel("INFO")).not.toBe("INFO");
    // UX-15: no unsourced claim about the city, no nested parentheses
    expect(departmentLabel("INFO")).not.toMatch(/city|\(/i);
  });

  it("a department filter keeps cases from both systems (REQ-WEB-MAP.2)", () => {
    const p: PointsFile = {
      data_version: "t", n: 3, id: ["a", "b", "c"], lat: [42.3, 42.3, 42.3], lon: [-71, -71, -71],
      tier: ["headline", "headline", "headline"], family: ["pothole_roadway", "pothole_roadway", "pothole_roadway"],
      department: ["PWDx", "Public Works Department (PWD)", "BTDT"], neighborhood: ["x", "x", "x"], year: [2020, 2026, 2020],
    };
    const rows = pointsToRows(p);
    const r = visibleSet(rows, { neighborhoods: [], departments: ["PWDx"], families: [], years: [] }, "headline");
    expect(r.items.map((i) => i.id).sort()).toEqual(["a", "b"]);
  });
});

describe("unassigned neighborhoods (REQ-WEB-CHARTS.2, UX-20)", () => {
  it("reads 'Neighborhood not recorded' for a neighborhood and plain 'Unknown' for other groupings", () => {
    expect(groupLabel("neighborhood", "unknown")).toBe("Neighborhood not recorded");
    expect(groupLabel("department", "unknown")).toBe("Unknown");
  });
});
