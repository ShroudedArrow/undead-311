---
inclusion: fileMatch
fileMatchPattern: ["web/src/copy/**", "web/src/**/*.tsx", "docs/**", "README.md", "drafts/**"]
---
# Voice and copy rules

## Voice
Plain, specific, a little dry. We sound like a careful neighbor who checked the records, not a startup. Name real places (Dorchester Ave, Mattapan), real numbers, real dates. Sentence case. Active voice. Plain verbs. Each piece of text does one job.

## Human-written copy only (Kiro leaves placeholders)
These are written by the team, not generated. Kiro inserts `TODO-COPY: <what this text must say>` and moves on:
- Hero line and subtitle; About/team section; Methods page introduction; error and empty-state voice samples; Devpost description; blog post; social post; video script.
All interface text lives in `web/src/copy/en.json` (and `es.json`), never hard-coded in components, so people can review and rewrite it in one place. `make copy-lint` scans those files, docs, README, and drafts (not code) and must report zero TODO-COPY markers before the Dec 2 freeze.

## Interface writing
- Buttons say exactly what happens ("Show zombies near me", not "Get started"). Same verb through the whole flow.
- Errors say what happened and how to fix it; they don't apologize.
- Empty states invite action ("No possible zombies on this block. Try widening the window to 90 days.").

## Banned words and phrases (copy-lint flags these)
delve, seamless/seamlessly, leverage, unlock, empower, robust, cutting-edge, game-changer, revolutionize, harness, elevate, supercharge, effortless/effortlessly, embark, tapestry, testament to, in the realm of, navigate the complexities, in today's fast-paced world, it's not just X it's Y, whether you're X or Y, at the end of the day, introducing.

## Banned patterns
Rhetorical-question openers; reflexive groups of three; emoji bullets or emoji headers; exclamation marks; Title Case Headings; more than one em dash per paragraph; badge walls in the README.

## Evidence over adjectives
Replace every adjective claim with a fact: not "a powerful analysis" but "checked 1.9 million cases since 2015" (use the real number).
