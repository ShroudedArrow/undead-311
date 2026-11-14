/**
 * Parsers for every exported file (REQ-WEB-DATA.1). Each wraps a validator generated from /schemas by
 * scripts/gen-parsers.mjs (ajv standalone, so the CSP needs no eval) and returns a result instead of throwing,
 * so one bad file only breaks its own panel (REQ-WEB-DATA.2).
 */
import type {
  BulkClosuresFile,
  CardShard,
  ExcessFile,
  ExclusionsFile,
  FunnelFile,
  GroupsFile,
  JudgeTourFile,
  PointsFile,
  ScorecardFile,
  StatusFile,
  SurvivalFile,
  TemporaryFixesFile,
  ValidationFile,
  ZombiesFile,
} from "./generated/types";
import validateBulkClosures from "./generated/validators/bulk_closures";
import validateCard from "./generated/validators/card";
import validateExcess from "./generated/validators/excess";
import validateExclusions from "./generated/validators/exclusions";
import validateFunnel from "./generated/validators/funnel";
import validateGroups from "./generated/validators/groups";
import validateJudgeTour from "./generated/validators/judge_tour";
import validatePoints from "./generated/validators/points";
import validateScorecard from "./generated/validators/scorecard";
import validateStatus from "./generated/validators/status";
import validateSurvival from "./generated/validators/survival";
import validateTemporaryFixes from "./generated/validators/temporary_fixes";
import validateValidation from "./generated/validators/validation";
import validateZombies from "./generated/validators/zombies";

export type ParseResult<T> = { ok: true; data: T } | { ok: false; error: string };

interface Validator {
  (data: unknown): boolean;
  errors?: { instancePath: string; message?: string; params?: Record<string, unknown> }[] | null;
}

/** Run a standalone validator and turn its first error into a short readable reason. */
export function runValidator<T>(validate: Validator, data: unknown): ParseResult<T> {
  if (validate(data)) return { ok: true, data: data as T };
  const e = validate.errors?.[0];
  if (!e) return { ok: false, error: "does not match its schema" };
  const where = e.instancePath === "" ? "top level" : e.instancePath;
  const extra = e.params && "missingProperty" in e.params ? ` (${String(e.params.missingProperty)})` : "";
  return { ok: false, error: `${where}: ${e.message ?? "invalid"}${extra}` };
}

export const parseZombies = (d: unknown) => runValidator<ZombiesFile>(validateZombies, d);
export const parseCardShard = (d: unknown) => runValidator<CardShard>(validateCard, d);
export const parsePoints = (d: unknown) => runValidator<PointsFile>(validatePoints, d);
export const parseScorecard = (d: unknown) => runValidator<ScorecardFile>(validateScorecard, d);
export const parseStatus = (d: unknown) => runValidator<StatusFile>(validateStatus, d);
export const parseJudgeTour = (d: unknown) => runValidator<JudgeTourFile>(validateJudgeTour, d);
export const parseValidation = (d: unknown) => runValidator<ValidationFile>(validateValidation, d);
export const parseSurvival = (d: unknown) => runValidator<SurvivalFile>(validateSurvival, d);
export const parseFunnel = (d: unknown) => runValidator<FunnelFile>(validateFunnel, d);
export const parseGroups = (d: unknown) => runValidator<GroupsFile>(validateGroups, d);
export const parseExcess = (d: unknown) => runValidator<ExcessFile>(validateExcess, d);
export const parseTemporaryFixes = (d: unknown) => runValidator<TemporaryFixesFile>(validateTemporaryFixes, d);
export const parseExclusions = (d: unknown) => runValidator<ExclusionsFile>(validateExclusions, d);
export const parseBulkClosures = (d: unknown) => runValidator<BulkClosuresFile>(validateBulkClosures, d);

export type Curve = SurvivalFile["curves"][number];
export type Group = GroupsFile["groups"][number];
export type FunnelLimit = FunnelFile["limits"][number];
export type ExcessRow = ExcessFile["rows"][number];
export type { BulkClosuresFile, ExcessFile, ExclusionsFile, FunnelFile, GroupsFile, SurvivalFile, TemporaryFixesFile };

export type Zombie = ZombiesFile["zombies"][number] & { resurrection_date?: string };
export type Card = CardShard["cards"][number];
export type CaseRecord = Card["original"];
export type Scorecard = ScorecardFile["scorecards"][number];
export type Rate = Scorecard["on_time"];
export type { CardShard, JudgeTourFile, PointsFile, ScorecardFile, StatusFile, ValidationFile, ZombiesFile };
