import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FOOTER_KEY } from "../lib/footerPref";
import { t } from "../lib/t";
import { Footer } from "./Footer";

/** REQ-WEB-DESIGN.3: the independence bar collapses to a one-line note, reopens, and remembers the choice. */
describe("Footer (REQ-WEB-DESIGN.3)", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("starts open with the full notice and the license credits", () => {
    render(<Footer />);
    expect(screen.getByText(t("app.footer_independent"))).toBeTruthy();
    expect(screen.getByText(t("app.footer_data_license"))).toBeTruthy();
    expect(screen.getByRole("button", { name: t("app.footer_close") })).toBeTruthy();
  });

  it("collapses to the one-line note, remembers it, and reopens on click", () => {
    const { unmount } = render(<Footer />);
    fireEvent.click(screen.getByRole("button", { name: t("app.footer_close") }));
    expect(screen.queryByText(t("app.footer_data_license"))).toBeNull();
    const note = screen.getByRole("button", { name: "Independent project, not affiliated with the City of Boston" });
    expect(window.localStorage.getItem(FOOTER_KEY)).toBe("1");
    unmount();
    render(<Footer />); // a later visit starts collapsed
    expect(screen.queryByText(t("app.footer_data_license"))).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: note.textContent ?? "" }));
    expect(screen.getByText(t("app.footer_data_license"))).toBeTruthy();
    expect(screen.getByText(t("app.footer_fonts_license"))).toBeTruthy();
    expect(window.localStorage.getItem(FOOTER_KEY)).toBeNull();
  });

  it("shows the full bar with no close button when pinned (methods page), even if the visitor collapsed it", () => {
    window.localStorage.setItem(FOOTER_KEY, "1");
    render(<Footer pinned />);
    expect(screen.getByText(t("app.footer_independent"))).toBeTruthy();
    expect(screen.getByText(t("app.footer_osm_license"))).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("works when storage throws: reads as open, and collapsing still works for the visit", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("blocked"); });
    render(<Footer />);
    fireEvent.click(screen.getByRole("button", { name: t("app.footer_close") }));
    expect(screen.queryByText(t("app.footer_data_license"))).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: t("app.footer_note") }));
    expect(screen.getByText(t("app.footer_data_license"))).toBeTruthy();
  });
});
