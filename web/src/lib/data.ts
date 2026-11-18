/**
 * Same-origin data loading (REQ-WEB-DATA.1-2, REQ-WEB-PERF.2). Every file goes through a schema-derived parser;
 * a failure becomes an error state for that panel only.
 */
import { useEffect, useState } from "react";
import type { ParseResult } from "./parse";
import { statsPath } from "./statsFiles";

export type Load<T> =
  | { status: "loading" }
  | { status: "ok"; data: T }
  | { status: "error"; file: string; error: string };

export function dataUrl(file: string): string {
  return `${import.meta.env.BASE_URL}data/${statsPath(file)}`;
}

export async function loadData<T>(file: string, parse: (d: unknown) => ParseResult<T>): Promise<Load<T>> {
  try {
    const res = await fetch(dataUrl(file));
    if (!res.ok) return { status: "error", file, error: `HTTP ${res.status}` };
    const json: unknown = await res.json();
    const parsed = parse(json);
    return parsed.ok ? { status: "ok", data: parsed.data } : { status: "error", file, error: parsed.error };
  } catch (e) {
    return { status: "error", file, error: e instanceof Error ? e.message : "request failed" };
  }
}

/**
 * Frozen judging-snapshot copy of a file (REQ-OPS-SNAP.2, issue 161 in the ops repo): `data/frozen/<same path>`. Judge mode reads it so the tour stays on
 * the judging snapshot after a nightly refresh. When `frozen/` is absent (local dev, committed fixtures; a static host may answer a
 * missing path with the app shell, which is not JSON) it falls back to the live file. A frozen file that is present but fails its schema
 * is an error, never a silent switch to live data.
 */
export async function loadFrozen<T>(file: string, parse: (d: unknown) => ParseResult<T>): Promise<Load<T>> {
  let json: unknown;
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}data/frozen/${statsPath(file)}`);
    if (!res.ok) return loadData(file, parse);
    json = await res.json();
  } catch {
    return loadData(file, parse);
  }
  const parsed = parse(json);
  return parsed.ok ? { status: "ok", data: parsed.data } : { status: "error", file: `frozen/${statsPath(file)}`, error: parsed.error };
}

const cache = new Map<string, Promise<Load<unknown>>>();
/** Results that have already come back, so a component that mounts later starts with its data and does not flash "loading" (layout shift). */
const settled = new Map<string, Load<unknown>>();
/** Record a result only while its promise is still the cached one, so a load that finishes after the cache was cleared cannot leave a stale result behind. */
const remember = <T,>(key: string, load: Promise<Load<T>>): Promise<Load<T>> => {
  const p: Promise<Load<T>> = load.then((r) => {
    if (cache.get(key) === (p as Promise<Load<unknown>>)) settled.set(key, r);
    return r;
  });
  return p;
};

/** Load once per file per page view; later callers share the promise. */
export function loadOnce<T>(file: string, parse: (d: unknown) => ParseResult<T>): Promise<Load<T>> {
  let p = cache.get(file);
  if (!p) {
    p = remember(file, loadData(file, parse));
    cache.set(file, p);
  }
  return p as Promise<Load<T>>;
}

/** `loadFrozen`, once per file per page view. */
export function loadFrozenOnce<T>(file: string, parse: (d: unknown) => ParseResult<T>): Promise<Load<T>> {
  const key = `frozen:${file}`;
  let p = cache.get(key);
  if (!p) {
    p = remember(key, loadFrozen(file, parse));
    cache.set(key, p);
  }
  return p as Promise<Load<T>>;
}

export function clearDataCache(): void {
  cache.clear();
  settled.clear();
}

export function useData<T>(file: string | null, parse: (d: unknown) => ParseResult<T>, frozen = false): Load<T> {
  const key = file === null ? null : frozen ? `frozen:${file}` : file;
  const [state, setState] = useState<Load<T>>(() => (key !== null ? (settled.get(key) as Load<T> | undefined) : undefined) ?? { status: "loading" });
  useEffect(() => {
    if (file === null) return;
    let live = true;
    const known = settled.get(frozen ? `frozen:${file}` : file) as Load<T> | undefined;
    setState(known ?? { status: "loading" });
    void (frozen ? loadFrozenOnce(file, parse) : loadOnce(file, parse)).then((r) => live && setState(r));
    return () => {
      live = false;
    };
    // `parse` is a module-level function; the file name is the only real dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);
  return state;
}
