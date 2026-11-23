import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MapLegend } from "./MapLegend";

const openKey = () => {
  const details = screen.getByTestId("map-legend") as HTMLDetailsElement;
  details.open = true;
  fireEvent(details, new Event("toggle"));
  return details;
};

describe("map key (REQ-WEB-MAP.1, REQ-WEB-A11Y.1)", () => {
  it("has a visible close button that shuts the key and puts focus back on the Map key button", () => {
    render(<MapLegend showOutline={false} />);
    const details = openKey();
    const close = screen.getByRole("button", { name: "Close map key" });
    expect(close.textContent).toBe("×");
    fireEvent.click(close);
    expect(details.open).toBe(false);
    expect(document.activeElement).toBe(details.querySelector("summary"));
  });
  it("shuts on Escape too, with focus on the Map key button", () => {
    render(<MapLegend showOutline={false} />);
    const details = openKey();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(details.open).toBe(false);
    expect(document.activeElement).toBe(details.querySelector("summary"));
  });
  it("lists the cluster mark only where the map clusters", () => {
    const { rerender } = render(<MapLegend showOutline={false} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(8);
    rerender(<MapLegend showOutline={false} showCluster={false} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(7);
  });
});
