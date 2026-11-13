import en from "../copy/en.json";

type Tree = { [key: string]: string | Tree };

/** Look up a user-facing string by dotted key (REQ-WEB-COPY). Unknown keys return the key so gaps are visible. */
export function t(key: string, tree: Tree = en as Tree): string {
  let node: string | Tree | undefined = tree;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === undefined) return key;
    node = node[part];
  }
  return typeof node === "string" ? node : key;
}
