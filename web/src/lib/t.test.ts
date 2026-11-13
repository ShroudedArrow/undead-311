import { describe, expect, it } from "vitest";
import { t } from "./t";

describe("t() copy helper (REQ-WEB-COPY)", () => {
  it("returns the string for a known key", () => {
    expect(t("app.title")).toBe("The Undead 311");
  });
  it("returns the key for an unknown key", () => {
    expect(t("no.such.key")).toBe("no.such.key");
  });
});
