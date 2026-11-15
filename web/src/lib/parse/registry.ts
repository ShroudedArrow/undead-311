/** Every generated validator by schema stem. Used by the contract test (REQ-WEB-DATA.1, testing.md #16); not by the app. */
import validateBulkClosures from "./generated/validators/bulk_closures";
import validateCard from "./generated/validators/card";
import validateExcess from "./generated/validators/excess";
import validateExclusions from "./generated/validators/exclusions";
import validateFunnel from "./generated/validators/funnel";
import validateGroups from "./generated/validators/groups";
import validateIncidents from "./generated/validators/incidents";
import validateJudgeTour from "./generated/validators/judge_tour";
import validatePoints from "./generated/validators/points";
import validateRepeatOffenders from "./generated/validators/repeat_offenders";
import validateScorecard from "./generated/validators/scorecard";
import validateSensitivityGrid from "./generated/validators/sensitivity_grid";
import validateSeparateDeaths from "./generated/validators/separate_deaths";
import validateStatus from "./generated/validators/status";
import validateSurvival from "./generated/validators/survival";
import validateTemporaryFixes from "./generated/validators/temporary_fixes";
import validateTrends from "./generated/validators/trends";
import validateValidation from "./generated/validators/validation";
import validateZombies from "./generated/validators/zombies";
import { runValidator, type ParseResult } from "./index";

export const REGISTRY: Record<string, (d: unknown) => ParseResult<unknown>> = Object.fromEntries(
  Object.entries({
    bulk_closures: validateBulkClosures,
    card: validateCard,
    excess: validateExcess,
    exclusions: validateExclusions,
    funnel: validateFunnel,
    groups: validateGroups,
    incidents: validateIncidents,
    judge_tour: validateJudgeTour,
    points: validatePoints,
    repeat_offenders: validateRepeatOffenders,
    scorecard: validateScorecard,
    sensitivity_grid: validateSensitivityGrid,
    separate_deaths: validateSeparateDeaths,
    status: validateStatus,
    survival: validateSurvival,
    temporary_fixes: validateTemporaryFixes,
    trends: validateTrends,
    validation: validateValidation,
    zombies: validateZombies,
  }).map(([k, v]) => [k, (d: unknown) => runValidator(v, d)]),
);
