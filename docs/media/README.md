# Media captured from the live site

Captured on 2026-11-23 from https://undead311.netlify.app, built from tag `judged-2026-11-19-final`. The site's `status.json` reported data version `2026-11-20+27ceb33+89e078da` and data end 2026-11-19, which match `data/SNAPSHOT.md`.

Regenerate with `node ops/capture/live.mjs --base https://undead311.netlify.app` (Playwright from `web/node_modules`; the GIF clips also need Pillow, `pip install pillow`).

- `screenshots/desktop-*.png`: 1280 x 800 px, one per page (14).
- `screenshots/phone-*.png`: 390 px wide viewport (Pixel 7 emulation at 2.625x, so the files are 1024 px wide), one per page (14). The card, neighborhood and district pages use the Stuart St and Kneeland St card (`101002329140:101002356770`, Downtown / Financial District, district 1C).
- `clips/home-map-zoom.gif` (8.5 s): home map from city view to street level.
- `clips/night-of-the-living-311.gif` (9.3 s): the time-lapse, scrubbed from its first date to Nov 19, 2026.
- `clips/autopsy-card-second-opinion.gif` (9.5 s): the Stuart St and Kneeland St card opening, then scrolling to its Second opinion (verdict: the objections did not hold up).
- `gallery/*-3x2.png`: five Devpost gallery images, 2400 x 1600 px (exactly 3:2), each under 5 MB. Rendered in a 1200 x 800 viewport at 2x, not cropped.

The app's own not-found page is not captured: an unknown address on the live site shows Netlify's generic 404 page.
