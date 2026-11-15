import { useEffect, useState } from "react";
import { neighborhoodImagePath, zombieImagePath } from "../lib/share";
import { t } from "../lib/t";

/** Copies the current address, so any view can be shared (REQ-WEB-LINKS.1). Falls back to showing the address when the clipboard is not available. */
export function CopyLink() {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setState("copied");
    } catch {
      setState("failed");
    }
  };
  return (
    <span className="copy-link">
      <button type="button" onClick={copy}>{t("share.copy_link")}</button>
      <span role="status" className="count-note">
        {state === "copied" ? t("share.copied") : state === "failed" ? t("share.copy_failed", { url: window.location.href }) : ""}
      </span>
    </span>
  );
}

/** True when `url` answers with an image (a static host may answer a missing file with the app shell, so the type is checked). */
export function useImageExists(url: string): boolean {
  const [ok, setOk] = useState(false);
  useEffect(() => {
    let live = true;
    setOk(false);
    fetch(url, { method: "HEAD" })
      .then((r) => live && setOk(r.ok && (r.headers.get("content-type") ?? "").startsWith("image/")))
      .catch(() => live && setOk(false));
    return () => {
      live = false;
    };
  }, [url]);
  return ok;
}

/** Permalink button and the share image for one possible zombie (REQ-WEB-LINKS.1-2). The image link appears only when the build rendered it. */
export function CardShare({ zombieId }: { zombieId: string }) {
  const href = `${import.meta.env.BASE_URL}${zombieImagePath(zombieId)}`;
  const has = useImageExists(href);
  return (
    <p className="card-share">
      <CopyLink />
      {has ? <a href={href} download>{t("share.image_link")}</a> : null}
    </p>
  );
}

/** The share image for one neighborhood, when the build rendered it (REQ-WEB-LINKS.2). */
export function NeighborhoodShareLink({ name }: { name: string }) {
  const href = `${import.meta.env.BASE_URL}${neighborhoodImagePath(name)}`;
  const has = useImageExists(href);
  return has ? <a href={href} download>{t("share.image_link")}</a> : null;
}
