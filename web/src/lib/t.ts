import en from "../copy/en.json";

type Tree = { [key: string]: string | Tree };
export type Params = Record<string, string | number>;

/**
 * Look up a user-facing string by dotted key and fill `{name}` slots (REQ-WEB-COPY.1).
 * Unknown keys return the key so gaps are visible.
 */
export function t(key: string, params?: Params, tree: Tree = en as Tree): string {
  let node: string | Tree | undefined = tree;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === undefined) return key;
    node = node[part];
  }
  if (typeof node !== "string") return key;
  if (!params) return node;
  return node.replace(/\{(\w+)\}/g, (m, name: string) => (name in params ? String(params[name]) : m));
}

/** True when a copy string is still a human-written placeholder (REQ-WEB-COPY.2). */
export function isTodoCopy(text: string): boolean {
  return text.startsWith("TODO-COPY:");
}
