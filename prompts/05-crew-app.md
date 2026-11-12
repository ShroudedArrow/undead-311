# 05 — Kiro Crew App (separate repo: undead-311-crew)

Setup:
1. Install Crew (desktop app, or `curl -fsSL https://download.crew.kiro.dev/cli.sh | sh`), then `kirocrew setup`, `kirocrew doctor`, `kirocrew gateway`. Dashboard: http://localhost:5476.
2. Create a Discord bot and server channel; set `DISCORD_BOT_TOKEN` in Crew's environment (`~/.kiro/crew/.env`).
3. In Kiro, read the Crew "Build your first app" and manifest docs (use the fetch/context tools), then:

"Create a Kiro Crew app in this repo: app.json manifest, agents/ (herald, coroner, skeptic adapted from the main repo), skills/, a small ui/ dashboard panel showing this week's zombies, and scripts/install.sh. Schedule: daily job labels new closure texts with the coroner and runs the skeptic on new possible zombies (reading the published data files from the main site); weekly job has the herald post the Resurrection Report to the Discord channel. Daily digest (8 AM): summarize the last 24 hours (commits by agent, open findings, failing checks, `needs-human` items) as one comment in the agent channel and one short Discord message to the team, so three people can coordinate without meetings.

Human gate through the channel: the herald posts each week's draft report as an issue in `ShroudedArrow/undead-311-ops` labeled `needs-human`; the Crew job posts it to Discord only after a teammate adds the `approved` label. Also: answer Discord questions like "any zombies near Dudley St?" using the Undead 311 MCP server, replying with plain-language results and permalinks. Add a README explaining features for the Best Kiro Crew App write-up."

For judging (Dec 16 – Jan 29), keep Crew running 24/7 in Docker on a small always-on machine if you want live reports; the main site does NOT depend on Crew.
