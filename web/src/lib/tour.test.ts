import { execFileSync, spawnSync } from "node:child_process";
import { join } from "node:path";
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { checkTour, next, previous, secondsLeft, START_CLOCK, stepMs, tick, togglePause, TOUR_SECONDS, type TourClock } from "./tour";

const arbIds = fc.uniqueArray(fc.string({ minLength: 1, maxLength: 6 }), { minLength: 3, maxLength: 3 });

describe("Property W8: a judging build accepts a tour only if every ID is confirmed (REQ-WEB-JUDGE.2)", () => {
  it("accepts iff final and all ids confirmed", () => {
    fc.assert(
      fc.property(arbIds, fc.boolean(), fc.array(fc.string({ minLength: 1, maxLength: 6 }), { maxLength: 8 }), (ids, provisional, extra) => {
        const confirmed = [...extra, ...ids.slice(0, 3)];
        const r = checkTour({ provisional, zombie_ids: ids }, { confirmed }, true);
        expect(r.ok).toBe(!provisional);
      }),
    );
  });
  it("rejects when any one id is unconfirmed", () => {
    fc.assert(
      fc.property(arbIds, fc.integer({ min: 0, max: 2 }), (ids, drop) => {
        const confirmed = ids.filter((_, i) => i !== drop);
        const r = checkTour({ provisional: false, zombie_ids: ids }, { confirmed }, true);
        expect(r.ok).toBe(false);
        expect(r.errors.some((e) => e.includes(ids[drop]))).toBe(true);
      }),
    );
  });
  it("rejects when there is no validation file at all", () => {
    expect(checkTour({ provisional: false, zombie_ids: ["a", "b", "c"] }, null, true).ok).toBe(false);
  });
  it("lets other builds play a provisional tour (REQ-WEB-JUDGE.3) but still wants three distinct zombies", () => {
    expect(checkTour({ provisional: true, zombie_ids: ["a", "b", "c"] }, { confirmed: [] }, false).ok).toBe(true);
    expect(checkTour({ provisional: true, zombie_ids: ["a", "b"] }, null, false).ok).toBe(false);
    expect(checkTour({ provisional: true, zombie_ids: ["a", "a", "c"] }, null, false).ok).toBe(false);
  });
});

describe("check-tour build script (REQ-WEB-JUDGE.2)", () => {
  const cwd = join(__dirname, "..", "..");
  it("passes on the provisional fixture tour in a normal build", () => {
    expect(execFileSync("node", ["scripts/check-tour.ts"], { cwd, encoding: "utf8" })).toContain("provisional tour");
  });
  it("fails the JUDGING=1 build while the tour is provisional", () => {
    const r = spawnSync("node", ["scripts/check-tour.ts"], { cwd, encoding: "utf8", env: { ...process.env, JUDGING: "1" } });
    expect(r.status).toBe(1);
    expect(r.stderr).toContain("provisional");
  });
});

describe("tour clock (REQ-WEB-JUDGE.1)", () => {
  it("takes about 60 seconds end to end", () => {
    expect(stepMs(3) * 3).toBe(TOUR_SECONDS * 1000);
    let c: TourClock = START_CLOCK;
    let t = 0;
    while (!c.done && t < 200000) {
      c = tick(c, 250, 3);
      t += 250;
    }
    expect(c.done).toBe(true);
    expect(Math.abs(t - 60000)).toBeLessThanOrEqual(250);
  });
  it("does not move while paused and resumes", () => {
    const paused = togglePause(START_CLOCK);
    expect(tick(paused, 5000, 3)).toEqual(paused);
    expect(tick(togglePause(paused), 5000, 3).elapsedMs).toBe(5000);
  });
  it("keeps the step in range and seconds left non-negative for any sequence of actions", () => {
    const action = fc.constantFrom("tick", "next", "prev", "pause");
    fc.assert(
      fc.property(fc.array(fc.tuple(action, fc.integer({ min: 1, max: 30000 })), { maxLength: 40 }), fc.integer({ min: 1, max: 5 }), (acts, steps) => {
        let c: TourClock = START_CLOCK;
        for (const [a, dt] of acts) {
          c = a === "tick" ? tick(c, dt, steps) : a === "next" ? next(c, steps) : a === "prev" ? previous(c) : togglePause(c);
          expect(c.step).toBeGreaterThanOrEqual(0);
          expect(c.step).toBeLessThan(steps);
          expect(c.elapsedMs).toBeGreaterThanOrEqual(0);
          expect(secondsLeft(c, steps)).toBeGreaterThanOrEqual(0);
          expect(secondsLeft(c, steps)).toBeLessThanOrEqual(TOUR_SECONDS);
        }
      }),
    );
  });
  it("next on the last step finishes the tour", () => {
    expect(next({ ...START_CLOCK, step: 2 }, 3).done).toBe(true);
    expect(next(START_CLOCK, 3).step).toBe(1);
  });
});
