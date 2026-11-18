import { useEffect, useState, type RefObject } from "react";
import { t } from "../lib/t";
import { useMedia } from "../lib/useMedia";

interface Item {
  id: string;
  text: string;
}

/** Wide enough for the contents list to sit beside a 70-character column (70rem = 1120 px at the default size). */
export const TOC_WIDE_QUERY = "(min-width: 70rem)";

/** Read the section headings (h2) under `root`, giving any heading without an id one, and follow the page as sections load. */
function useHeadings(root: RefObject<HTMLElement | null>): Item[] {
  const [items, setItems] = useState<Item[]>([]);
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const scan = () => {
      const next = [...el.querySelectorAll<HTMLHeadingElement>("h2")].map((h, i) => {
        if (!h.id) h.id = `section-${i + 1}`;
        return { id: h.id, text: h.textContent ?? "" };
      });
      setItems((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
    };
    scan();
    const mo = new MutationObserver(scan);
    mo.observe(el, { childList: true, subtree: true, characterData: true });
    return () => mo.disconnect();
  }, [root]);
  return items;
}

/**
 * Table of contents for a long page, built from the page's own h2 headings so it cannot drift from the content. On wide screens it is a
 * plain list that stays in view beside the column; on narrower screens it is one closed disclosure above the content.
 */
export function PageToc({ contentRef }: { contentRef: RefObject<HTMLElement | null> }) {
  const items = useHeadings(contentRef);
  const wide = useMedia(TOC_WIDE_QUERY);
  if (items.length === 0) return <nav className="toc" aria-label={t("methods.toc_heading")} />;
  const list = (
    <ol>
      {items.map((i) => (
        <li key={i.id}>
          <a href={`#${i.id}`}>{i.text}</a>
        </li>
      ))}
    </ol>
  );
  return (
    <nav className="toc" aria-label={t("methods.toc_heading")}>
      {wide ? (
        <>
          <p className="toc-title">{t("methods.toc_heading")}</p>
          {list}
        </>
      ) : (
        <details>
          <summary>{t("methods.toc_heading")}</summary>
          {list}
        </details>
      )}
    </nav>
  );
}
