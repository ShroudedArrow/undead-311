import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AutopsyCard } from "../components/AutopsyCard";
import { PageHeader } from "../components/PageHeader";
import { PanelError } from "../components/PanelError";
import { useData } from "../lib/data";
import { usePrefersReducedMotion } from "../lib/motion";
import { parseJudgeTour } from "../lib/parse";
import { t } from "../lib/t";
import { next, previous, secondsLeft, START_CLOCK, tick, togglePause, type TourClock } from "../lib/tour";
import { useTourCards } from "../lib/tourCards";

const TICK_MS = 250;

/**
 * Judge mode: a 60-second guided tour of three possible zombies (REQ-WEB-JUDGE.1, .3, .4). Skippable, pausable,
 * keyboard operable (space, arrows, escape). Under reduced motion it does not advance by itself.
 */
export default function JudgePage() {
  const tour = useData("judge_tour.json", parseJudgeTour, true);
  const cards = useTourCards(tour.status === "ok" ? tour.data.zombie_ids : null);
  const reduced = usePrefersReducedMotion();
  const navigate = useNavigate();
  const [clock, setClock] = useState<TourClock>(START_CLOCK);
  const [started, setStarted] = useState(false);
  const total = tour.status === "ok" ? tour.data.zombie_ids.length : 3;
  const root = useRef<HTMLDivElement>(null);

  const skip = useCallback(() => navigate("/"), [navigate]);

  useEffect(() => {
    if (!started || reduced || cards.status !== "ok") return;
    const id = window.setInterval(() => setClock((c) => tick(c, TICK_MS, total)), TICK_MS);
    return () => window.clearInterval(id);
  }, [started, reduced, cards.status, total]);

  useEffect(() => {
    if (!started) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const onControl = target?.closest("button, a, input, select, summary") != null;
      if (e.key === "Escape") skip();
      else if (e.key === "ArrowRight") setClock((c) => next(c, total));
      else if (e.key === "ArrowLeft") setClock((c) => previous(c));
      else if ((e.key === " " || e.code === "Space") && !onControl) {
        e.preventDefault();
        setClock((c) => togglePause(c));
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [started, total, skip]);

  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (started) heading.current?.focus();
  }, [started, clock.step, clock.done]);

  return (
    <div className="page judge form-sheet" ref={root}>
      <PageHeader title={t("judge.title")} />
      {tour.status === "error" && <PanelError file={tour.file} error={tour.error} />}
      {tour.status === "ok" && tour.data.provisional && (
        <p className="provisional-notice" role="note" data-testid="provisional-notice">
          <strong>{t("judge.provisional_label")}.</strong> {t("judge.provisional_notice")}
        </p>
      )}
      {tour.status === "ok" && !tour.data.provisional && tour.data.confirmation === "records" && (
        <p className="provisional-notice" role="note" data-testid="record-confirmed-notice">
          <strong>{t("judge.record_confirmed_label")}.</strong> {t("judge.record_confirmed_notice")}
        </p>
      )}
      {cards.status === "error" && <PanelError file={cards.file} error={cards.error} />}

      {!started && tour.status === "ok" && (
        <div>
          <p>{t("judge.intro")}</p>
          <p>{t("judge.keys")}</p>
          {reduced && <p>{t("judge.reduced_motion")}</p>}
          <p className="judge-actions">
            <button type="button" onClick={() => setStarted(true)} disabled={cards.status !== "ok"}>
              {t("judge.start")}
            </button>{" "}
            <Link to="/" className="button-link">
              {t("judge.skip")}
            </Link>
          </p>
        </div>
      )}

      {started && cards.status === "ok" && !clock.done && (
        <div data-testid="tour-step" data-step={clock.step}>
          <h2 tabIndex={-1} ref={heading}>
            {t("judge.step", { n: clock.step + 1, total })}
          </h2>
          {!reduced && (
            <p className="tour-progress" aria-live="off">
              {t("judge.progress", { seconds: secondsLeft(clock, total) })}
            </p>
          )}
          {reduced && <p>{t("judge.reduced_motion")}</p>}
          <div className="judge-actions" role="group" aria-label={t("judge.title")}>
            <button type="button" onClick={() => setClock((c) => previous(c))} disabled={clock.step === 0}>
              {t("judge.previous")}
            </button>
            {!reduced && (
              <button type="button" aria-pressed={clock.paused} onClick={() => setClock((c) => togglePause(c))}>
                {clock.paused ? t("judge.resume") : t("judge.pause")}
              </button>
            )}
            <button type="button" onClick={() => setClock((c) => next(c, total))}>
              {t("judge.next")}
            </button>
            <button type="button" onClick={skip}>
              {t("judge.skip")}
            </button>
          </div>
          <AutopsyCard card={cards.cards[clock.step]} recordConfirmed={tour.status === "ok" && !tour.data.provisional && tour.data.confirmation === "records"} />
        </div>
      )}

      {started && clock.done && (
        <div data-testid="tour-done">
          <h2 tabIndex={-1} ref={heading}>
            {t("judge.done")}
          </h2>
          <p>
            <Link to="/" className="button-link">
              {t("judge.to_map")}
            </Link>
          </p>
        </div>
      )}
    </div>
  );
}
