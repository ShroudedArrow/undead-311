import en from "../copy/en.json";
import es from "../copy/es.json";

type Tree = { [key: string]: string | string[] | Tree };
export type Params = Record<string, string | number>;
export type Lang = "en" | "es";

let current: Lang = "en";

/** The language `t()` answers in. Set by the app shell from the URL and the language switch (REQ-WEB-ES.1). */
export function setLang(lang: Lang): void {
  current = lang;
  if (typeof document !== "undefined") document.documentElement.lang = lang;
}
export const getLang = (): Lang => current;

function lookup(tree: Tree, key: string): string | undefined {
  let node: string | string[] | Tree | undefined = tree;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === undefined || Array.isArray(node)) return undefined;
    node = node[part];
  }
  return typeof node === "string" ? node : undefined;
}

/**
 * Look up a user-facing string by dotted key and fill `{name}` slots (REQ-WEB-COPY.1). In Spanish a missing key falls back to the
 * English string (REQ-WEB-ES.1). Unknown keys return the key so gaps are visible.
 */
export function t(key: string, params?: Params, tree?: Tree): string {
  const found = tree ? lookup(tree, key) : ((current === "es" ? lookup(es as Tree, key) : undefined) ?? lookup(en as Tree, key));
  if (found === undefined) return key;
  if (!params) return found;
  return found.replace(/\{(\w+)\}/g, (m, name: string) => (name in params ? String(params[name]) : m));
}

/** True when a copy string is still a human-written placeholder (REQ-WEB-COPY.2). */
export function isTodoCopy(text: string): boolean {
  return text.startsWith("TODO-COPY:");
}

/** Top-level sections of a copy file that an agent drafted and no person has reviewed yet (`_needs_review`). */
export function unreviewedSections(tree: Tree = es as Tree): string[] {
  const v = tree._needs_review;
  return Array.isArray(v) ? v : [];
}

/**
 * Spanish is offered only when it is safe to show (REQ-WEB-ES.1): every section is reviewed, or this is not a production build,
 * or the build sets VITE_SHOW_UNREVIEWED_ES=1 (a preview for the native-speaker reviewer).
 */
export function spanishAvailable(opts: { prod: boolean; preview: boolean; unreviewed?: readonly string[] }): boolean {
  const pending = opts.unreviewed ?? unreviewedSections();
  return pending.length === 0 || !opts.prod || opts.preview;
}
