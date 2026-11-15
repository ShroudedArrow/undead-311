import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import fc from "fast-check";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { permalink } from "../components/ShareLinks";
import { AutopsyCard, type CardWithPartial } from "../components/AutopsyCard";
import { Scorecard } from "../components/Scorecard";
import en from "../copy/en.json";
import es from "../copy/es.json";
import { clearDataCache } from "./data";
import { setLang, spanishAvailable, t, unreviewedSections } from "./t";

afterEach(() => { setLang("en"); vi.unstubAllGlobals(); clearDataCache(); });

type Tree = { [k: string]: unknown };
const leaves = (d: Tree, p = ""): string[] => Object.entries(d).flatMap(([k, v]) => (v && typeof v === "object" && !Array.isArray(v) ? leaves(v as Tree, `${p}${k}.`) : [`${p}${k}`]));
const slots = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
const get = (d: Tree, key: string) => key.split(".").reduce<unknown>((n, k) => (n as Tree)?.[k], d) as string;

describe("Spanish copy (REQ-WEB-ES.1)", () => {
  it("every Spanish key exists in English and keeps the same {slots}", () => {
    for (const k of leaves(es as Tree).filter((x) => !x.startsWith("_"))) {
      expect(get(en as Tree, k), k).toBeTypeOf("string");
      expect(slots(get(es as Tree, k)), k).toEqual(slots(get(en as Tree, k)));
    }
  });
  it("covers every string of the autopsy card and the scorecard, and the labels they use", () => {
    for (const section of ["card", "score", "labels", "families"]) {
      const missing = leaves((en as Tree)[section] as Tree, `${section}.`).filter((k) => typeof get(es as Tree, k) !== "string" && !["card.case_url", "card.fixture_notice"].includes(k));
      expect(missing, section).toEqual([]);
    }
  });
  it("marks every drafted section needs-review, with no TODO-COPY placeholder text in it", () => {
    const sections = Object.keys(es).filter((k) => !k.startsWith("_"));
    expect(unreviewedSections()).toEqual(expect.arrayContaining(sections));
    expect(JSON.stringify(es)).not.toContain("TODO-COPY");
  });
  it("is hidden in production while any section is unreviewed, and shown in dev, in a preview build, or once reviewed", () => {
    expect(spanishAvailable({ prod: true, preview: false, unreviewed: ["card"] })).toBe(false);
    expect(spanishAvailable({ prod: false, preview: false, unreviewed: ["card"] })).toBe(true);
    expect(spanishAvailable({ prod: true, preview: true, unreviewed: ["card"] })).toBe(true);
    expect(spanishAvailable({ prod: true, preview: false, unreviewed: [] })).toBe(true);
  });
  it("t() answers in Spanish, and falls back to English for a key with no Spanish", () => {
    setLang("es");
    expect(t("card.stamp_again")).toBe("REPORTADO DE NUEVO");
    expect(t("methods.title")).toBe(en.methods.title);
    expect(t("no.such.key")).toBe("no.such.key");
  });
  it("property: in either language every English key resolves to a string and slots survive", () => {
    const keys = leaves(en as Tree);
    fc.assert(fc.property(fc.constantFrom(...keys), fc.constantFrom("en", "es" as const), (k, l) => {
      setLang(l as "en" | "es");
      const out = t(k);
      return typeof out === "string" && out !== "" && slots(out).join() === slots(get((l === "es" && typeof get(es as Tree, k) === "string" ? es : en) as Tree, k)).join();
    }), { numRuns: 200 });
  });
  it("the shared link keeps the language", () => {
    expect(permalink("https://x.test/zombie/1?tier=all", "es")).toBe("https://x.test/zombie/1?tier=all&lang=es");
    expect(permalink("https://x.test/a?lang=es", "en")).toBe("https://x.test/a");
  });
});

describe("Spanish in the app (REQ-WEB-ES.1)", () => {
  const SC = { data_version: "v", scorecards: [{ family: "sign", tier_set: "headline", n_closed: 10, n_on_time_known: 10, on_time: { rate: 0.8, lo: 0.7, hi: 0.9, k: 8, n: 10 }, stayed_fixed_raw: { rate: 0.5, lo: 0.4, hi: 0.6, k: 5, n: 10 }, stayed_fixed_adj: null }], counts: { headline: 1, source_unknown: 0, city_rereport: 0, sensitivity: 0 }, params: { WINDOW_DAYS: 60, RADIUS_M: 30, matching: "segment" }, seed: null };
  it("switches the scorecard to Spanish from the language buttons, and back", async () => {
    vi.stubGlobal("fetch", vi.fn(async (u: string) => ({ ok: true, status: 200, headers: new Headers(), json: async () => (String(u).endsWith("scorecard.json") ? SC : { data_version: "v", last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" }) }) as Response));
    render(<MemoryRouter initialEntries={["/scorecard"]}><App /></MemoryRouter>);
    expect(await screen.findByText("Closed on time")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Español" }));
    expect(await screen.findByText("Cerrado a tiempo")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Señales" })).toBeTruthy();
    expect(document.documentElement.lang).toBe("es");
    fireEvent.click(screen.getByRole("button", { name: "English" }));
    expect(await screen.findByText("Closed on time")).toBeTruthy();
    expect(document.documentElement.lang).toBe("en");
  });
  it("opens in Spanish from ?lang=es", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, headers: new Headers(), json: async () => SC }) as Response));
    render(<MemoryRouter initialEntries={["/scorecard?lang=es"]}><App /></MemoryRouter>);
    expect(await screen.findByText("Cerrado a tiempo")).toBeTruthy();
  });
  it("renders the autopsy card and scorecard components in Spanish", () => {
    setLang("es");
    render(<Scorecard file={SC as never} />);
    expect(screen.getByText("El arreglo duró (sin ajustar)")).toBeTruthy();
  });
  it("renders the autopsy card in Spanish, with the cause of death, the gap and the stamps", () => {
    setLang("es");
    const card = { zombie_id: "1:2", original: { id: "1", system: "legacy", open_time: "2026-01-10T15:00:00Z", close_time: "2026-01-12T15:00:00Z", type_raw: "Pothole", status: "Closed", closure_text: "x", street: "A St", lat: 42.3, lon: -71 }, rereport: { id: "BCS-2", system: "new", open_time: "2026-01-20T15:00:00Z", close_time: null, type_raw: "Pothole", status: "Open", closure_text: null, street: "A St", lat: 42.3, lon: -71 }, cause_of_death: "made_safe_temporary", gap_days: 8.04, resurrection_date: "2026-01-20", confidence: 0.7, tier: "headline", skeptic_verdict: "survives", skeptic_notes: "", reports_after: 1, times_risen: 1, bulk_closure: false } as CardWithPartial;
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, headers: new Headers() }) as Response));
    render(<MemoryRouter><AutopsyCard card={card} /></MemoryRouter>);
    expect(screen.getByText("Asegurado por ahora")).toBeTruthy();
    expect(screen.getByText("8 días")).toBeTruthy();
    expect(screen.getByText("REPORTADO DE NUEVO")).toBeTruthy();
    expect(screen.getByText("Causa de la muerte")).toBeTruthy();
  });
});
