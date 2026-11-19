import { useLayoutEffect, useState } from "react";
import { t } from "../lib/t";

interface Item {
  id: string;
  text: string;
}

/** Read the section headings (h2) under `el`, giving any heading without an id one, and follow the page as sections load. */
function useHeadings(el: HTMLElement | null): Item[] {
  const [items, setItems] = useState<Item[]>([]);
  // before the first paint, so the list is there when the page first shows (layout shift)
  useLayoutEffect(() => {
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
  }, [el]);
  return items;
}

/**
 * Table of contents for a long page, built from the page's own h2 headings so it cannot drift from the content. A plain, static list
 * under the page title (two columns on wide screens, one on phones, app.css): nothing in it moves while the page scrolls.
 */
export function PageToc({ content }: { content: HTMLElement | null }) {
  const items = useHeadings(content);
  return (
    <nav className="toc" aria-labelledby="toc-title">
      <p className="toc-title" id="toc-title">{t("methods.toc_heading")}</p>
      {items.length > 0 ? (
        <ol>
          {items.map((i) => (
            <li key={i.id}>
              <a href={`#${i.id}`}>{i.text}</a>
            </li>
          ))}
        </ol>
      ) : null}
    </nav>
  );
}
