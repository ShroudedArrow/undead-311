/**
 * Judge-mode tour rules (REQ-WEB-JUDGE.1-3). Plain TypeScript with no runtime imports, so the build script
 * scripts/check-tour.ts can run it under Node and the app can run it in the browser.
 */
export interface TourFile {
  provisional: boolean;
  zombie_ids: readonly string[];
}
export interface ValidationFileLike {
  confirmed: readonly string[];
}

export const TOUR_SIZE = 3;
export const TOUR_SECONDS = 60;

export interface TourCheck {
  ok: boolean;
  errors: string[];
}

/**
 * The judging-build check (REQ-WEB-JUDGE.2): the tour is accepted only when it is not provisional and every zombie
 * ID is in the confirmed validation set. Other builds accept a provisional tour and show a notice (REQ-WEB-JUDGE.3).
 */
export function checkTour(tour: TourFile, validation: ValidationFileLike | null, judging: boolean): TourCheck {
  const errors: string[] = [];
  if (tour.zombie_ids.length !== TOUR_SIZE) errors.push(`the tour must list ${TOUR_SIZE} zombies, found ${tour.zombie_ids.length}`);
  if (new Set(tour.zombie_ids).size !== tour.zombie_ids.length) errors.push("the tour lists a zombie twice");
  if (judging) {
    if (tour.provisional) errors.push("judge_tour.json is provisional");
    const confirmed = new Set(validation?.confirmed ?? []);
    for (const id of tour.zombie_ids) if (!confirmed.has(id)) errors.push(`${id} is not in the confirmed validation set`);
  }
  return { ok: errors.length === 0, errors };
}

/** Tour clock: one state record, advanced by pure functions (REQ-WEB-JUDGE.1). */
export interface TourClock {
  step: number;
  elapsedMs: number;
  paused: boolean;
  done: boolean;
}

export const START_CLOCK: TourClock = { step: 0, elapsedMs: 0, paused: false, done: false };

export function stepMs(steps: number): number {
  return (TOUR_SECONDS * 1000) / Math.max(1, steps);
}

/** Advance by `dtMs`. A paused or finished clock does not move. Moving past the last step finishes the tour. */
export function tick(c: TourClock, dtMs: number, steps: number): TourClock {
  if (c.paused || c.done || dtMs <= 0) return c;
  const per = stepMs(steps);
  let elapsed = c.elapsedMs + dtMs;
  let step = c.step;
  while (elapsed >= per) {
    elapsed -= per;
    step += 1;
    if (step >= steps) return { ...c, step: steps - 1, elapsedMs: per, done: true };
  }
  return { ...c, step, elapsedMs: elapsed };
}

export function next(c: TourClock, steps: number): TourClock {
  if (c.step + 1 >= steps) return { ...c, step: steps - 1, elapsedMs: stepMs(steps), done: true };
  return { ...c, step: c.step + 1, elapsedMs: 0, done: false };
}

export function previous(c: TourClock): TourClock {
  return { ...c, step: Math.max(0, c.step - (c.done ? 0 : 1)), elapsedMs: 0, done: false };
}

export function togglePause(c: TourClock): TourClock {
  return c.done ? c : { ...c, paused: !c.paused };
}

/** Seconds left in the whole tour, for the progress text. */
export function secondsLeft(c: TourClock, steps: number): number {
  if (c.done) return 0;
  const per = stepMs(steps);
  return Math.max(0, Math.ceil(((steps - c.step) * per - c.elapsedMs) / 1000));
}
