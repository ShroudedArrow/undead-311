import { describe, expect, it } from "vitest";
import { isTodoCopy, t } from "./t";

describe("t() copy helper (REQ-WEB-COPY.1)", () => {
  it("returns the string for a known key", () => {
    expect(t("app.title")).toBe("The Undead 311");
  });
  it("returns the key for an unknown key", () => {
    expect(t("no.such.key")).toBe("no.such.key");
  });
  it("fills named slots and leaves unknown slots visible", () => {
    const tree = { a: { b: "Hello {who}, {missing}" } };
    expect(t("a.b", { who: "Boston" }, tree)).toBe("Hello Boston, {missing}");
  });
  it("flags TODO-COPY placeholders (REQ-WEB-COPY.2)", () => {
    expect(isTodoCopy(t("app.hero_line"))).toBe(true);
    expect(isTodoCopy(t("app.footer_independent"))).toBe(false);
  });
});
