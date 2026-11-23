---
inclusion: fileMatch
fileMatchPattern: ["**/web/**", "**/docs/screenshots/**"]
---
# Design system (TEAM-OWNED — confirm or change before the first UI build)

The look comes from the real world of Boston street repair, not from generic dashboards. Crews spray-paint circles around potholes and mark streets with color-coded utility paint; the city records work on typed, multi-copy forms. We reuse that vernacular: **the city circles a problem in paint; we circle the ones that came back.**

## Palette (proposal — 6 named values; the team may adjust)
| Name | Hex | Meaning |
|---|---|---|
| Concrete | #CDCBC6 | Page background (cool grey, not cream) |
| Asphalt | #2E3134 | Text, map streets and land |
| Crew white | #F4F4EF | The city's original "closed" marks on the map |
| Survey pink | #FF3EA5 | Possible zombies — the ONE loud color; never decorative |
| Cone orange | #F26B1D | Warnings only (bulk/backlog closures) |
| Canary copy | #EFE08A | The yellow carbon-copy layer of autopsy forms |
Color always carries meaning. No gradients.

## Type (proposal)
- **Public Sans** (the US government's open-source typeface) for UI and body text: civic, plain, legible.
- A typewriter face (e.g., Courier Prime) **only inside the autopsy forms**, where typed municipal paperwork is the subject. Never as decorative small labels elsewhere.
- Sentence case everywhere. One clear type scale. Body line length under ~75 characters.

## Layout
- The **map is the hero**: open on Boston with pink circles where problems came back. No marketing hero, no stat-plus-gradient banner, no "three feature cards" section.
- Autopsy cards look like **triplicate city forms** (white/canary/pink copies, slightly offset), with a "CLOSED" stamp struck through and re-stamped "REPORTED AGAIN". Real form structure: numbered boxes only where a form genuinely numbers fields.
- Leaderboards and charts are plain and disciplined; uncertainty intervals always visible.
- On phones, the triplicate form collapses to a single readable copy in a bottom sheet; the offset copies appear only on wider screens.
- Fonts are self-hosted (no font CDN).

## Signature assets (human-made)
- Zombie markers = **real spray-paint circles**: the project owner sprays chalk paint circles on cardboard, then photographs and vectorize them. No AI-generated images or illustrations anywhere.
- Photos = the team's own field-validation photos of Boston streets.
- Map style tuned by hand to this palette (do not ship a default dark basemap).

## Motion
- ONE orchestrated moment: the "Night of the Living 311" time-lapse where pink circles appear across the city.
- Everything else is still. Motion only in response to user action (a form pulled from the stack, a filter applied). Respect prefers-reduced-motion.

## Banned defaults (reviewers must reject these)
- Near-black background with one neon accent (especially zombie green); warm cream + serif + terracotta; purple/blue gradients; gradient washes; glassmorphism.
- Identical rounded cards with soft grey shadows; one border-radius on everything.
- Tracked ALL-CAPS eyebrow labels; "A · B · C" meta strings; "WORD — fragment" labels; "→" appended to buttons/links.
- Accenting a single headline word with color/italic/bold.
- 01/02/03 markers unless the content is truly a sequence.
- Fade-and-slide-up on every section; hover animation on every card.
- Emoji as icons; unstyled default icon packs; horror fonts, dripping blood, green slime.
- Default font stacks (Inter/Roboto/system) chosen by habit.
- Shipping any placeholder copy (see voice.md).

## Quality floor (non-negotiable)
Responsive to mobile, visible keyboard focus, WCAG AA contrast, reduced motion respected, table view mirrors the map.

## Contrast rules (measured)
- Asphalt on Concrete 8.1:1, on Canary 9.8:1, on Crew white 11.9:1: all fine for text.
- Survey pink on Concrete is only 2.0:1 and Cone orange on Concrete 1.9:1: **never use pink or orange for text**. On a light background, markers get an Asphalt outline.
- Pink on Asphalt 4.0:1 and orange on Asphalt 4.3:1: fine for map markers (graphics need 3:1), not for small text.
- Never rely on color alone: zombies also differ by shape (the spray circle) and in the table view.
Exceptions: Night of the Living 311 uses a dark "night shift" basemap (that page only). A short pink rule under the headline zombie count is allowed because it marks zombies; no other decorative pink.
