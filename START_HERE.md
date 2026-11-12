# START HERE — The Undead 311 (solo, minimum human hours)

*Thu Nov 12, 2026. 22 days to the deadline (Fri Dec 4, 2:00 PM PT). Kiro does the building; you do about 25 hours of work only a person can do.*

---

## 1. Before you open Kiro (about 1.5 hours, browser only)

1. **Check Kiro Web access.** Log in at app.kiro.dev. If your plan doesn’t include it, use the Azure fallback in `prompts/09-azure-runner.md` instead, and skip step 5 below.
2. **GitHub setup:**
   1. **Claim the Student Developer Pack** (education.github.com). It includes GitHub Pro, which you need for branch protection on private repos.
   2. **Create the five repos:** `undead-311` (private, with MIT license), `undead-311-crew`, `boston-311-power`, `undead-311-data` (each with MIT license), and `undead-311-ops` (**private**).
   3. **Upload the kit:** unzip it, open `undead-311` on GitHub, choose **Add file → Upload files**, and drag in everything, including the `.kiro` folder and the dotfiles. Afterward, check that `.kiro/` shows up in the repo. (Some browsers skip hidden folders; the checker also flags missing files.)
   4. **Protect `main`, after the upload:** Settings → Branches → require a pull request before merging.
3. **Create two tokens** (GitHub → Settings → Developer settings → Fine-grained tokens) and save both somewhere safe:
   - **Channel token:** access to `undead-311-ops` **only**; **Issues: Read and write**; expires mid-February.
   - **Audit token:** access to all five repos; **Administration, Contents, and Issues: Read only**.
4. **Paperwork:**
   - Create the Devpost project draft (solo).
   - Send the clarification email (text in the pre-flight checklist, B11).
   - Ask one friend to be your second validation rater: about 1 hour around Nov 22, rating your photos.
5. **Kiro Web settings:**
   - **Connect GitHub** with access to the five repos only.
   - **Settings → Sandbox:**
     - **Internet access:** Common dependencies, plus the allow-list entry `data.boston.gov`. (The checker later prints the exact download hosts to add.)
     - **Environment variable:** `DATA_DIR=/projects/sandbox/undead-311/.local-data/data`, `UV_CACHE_DIR=/projects/sandbox/undead-311/.local-data/uv-cache`
     - **Secrets:** `GITHUB_CHANNEL_TOKEN`, `GITHUB_AUDIT_TOKEN`
     - **Setup command:** `pip install uv` (only if `uv` is missing; Python 3.11 is preinstalled)

## 2. What to give Kiro, in order

Each line is a new session on the `undead-311` repo. Merge each session’s pull request before starting the next.

| # | Send this | Result |
|---|---|---|
| 1 | `Read prompts/00-setup-guide.md and follow it exactly.` | Walks you through Gate 1; fixes placeholders; creates labels; runs the channel smoke test |
| 2 | The full contents of `prompts/00-kickoff.md` | Data verified; **go/no-go** recorded; sample data and Makefile |
| 3 | `Read prompts/00-setup-guide.md and follow it exactly.` | Gate 2: walks you through agents (`01`), hooks (`02`), and spec drafts (`03`) |
| — | **You:** work out the test-town answers by hand (about 1.5 h; Kiro may draft the cases) and review the specs line by line (about 2 h) | The only quality gates that need you |
| 4 | `Read prompts/00-setup-guide.md and follow it exactly.` | Gate 3: smoke test, safety tests, final audit; writes `docs/READINESS.md`; posts a readiness issue |
| — | **You:** reply **GO** on the readiness issue | |
| 5 | `Run .kiro/workflows/build-undead-311.workflow.yaml as an unattended run. Follow the unattended-run rule in structure.md.` | The overnight build. Close the browser |

After that, the loop is: read the morning report in the agent channel and the pull request (about 20 minutes), merge or file a fix, start the next run.

## 3. Your hours (about 25 total)

| Task | Hours | Why it can’t be delegated |
|---|---|---|
| Accounts, tokens, settings, upload | 1.5 | Your identity and your security decisions |
| Test-town answer key | 1.5 | Must be independent of the code it tests |
| Spec review | 2 | The highest-leverage human check |
| Morning reviews (about 20 days) | 6–7 | You approve every merge |
| Field validation (40–50 sites in 3–4 nearby neighborhoods) | 4 | Someone has to look at the street |
| Two short user chats | 1 | Real quotes for Impact |
| Spray-paint circles and design pass | 1.5 | The human-made signature |
| Copy pass (key interface text) | 1.5 | Keeps it from reading as AI-generated |
| Video: script, record, edit | 4.5 | Your voice and your footage |
| Write-up and Devpost text | 2 | Judged on authenticity |

**Hour-savers, on by default** (turn any back on if you’re ahead by Nov 24):
- **The Crew App is skipped.** It’s a $1K bonus, only judged among the top 50, and it needs Docker or a Mac.
- **The blog post and social post are skipped.** They pay out in credits or a subscription, not cash.
- **The test town is 30 cases**, not 60, and Kiro drafts the cases.
- **Validation is 40–50 sites, clustered near you**, with the clustering stated as a limitation.

## 4. Timeline (re-baselined)

| Dates | Milestone |
|---|---|
| Thu Nov 12 | Section 1; sessions 1–2 |
| Fri Nov 13 | Session 3; test-town answers |
| Sat Nov 14 | Spec review; session 4; **first overnight build** |
| Sun Nov 15 – Tue Nov 17 | Fix and rebuild. **Demo-critical layer done by Tue** |
| Wed Nov 18 – Fri Nov 20 | Credibility layer. **Fri: freeze snapshot and draw the validation sample** |
| Sat Nov 21 – Sun Nov 22 | Field validation; user chats; spray circles |
| Mon Nov 23 – Wed Nov 25 | Delight layer only if on track; media capture; copy and design pass |
| Thu Nov 26 | Thanksgiving |
| Fri Nov 27 – Sun Nov 29 | Video |
| Mon Nov 30 – Tue Dec 1 | Write-up; Devpost; final readiness check |
| **Wed Dec 2 / Thu Dec 3** | **Freeze / submit** (Fri Dec 4 is buffer) |

**Cut lines are automatic:**
- If the demo-critical layer isn’t working by **Tue Nov 17**, the delight layer is dropped.
- If credibility isn’t done by **Sun Nov 22**, the Power repo is dropped too.

## 5. Pre-start audit (Nov 12): what was found and fixed

| # | Finding | Fix | Status |
|---|---|---|---|
| 1 | **The timeline was three weeks stale.** It still started Oct 30, and “demo-critical by Nov 15” left 3 days | Re-baselined from today; cut lines moved to Nov 17 and Nov 22 | Fixed (write-up, this page) |
| 2 | Leftover team-era instructions (teammates, “Kiro lead,” invites) in six prompt and steering files | Rewritten for one person | Fixed |
| 3 | Hooks and the audit depended on `gh` and `jq`, which a cloud sandbox may not have | Python standard library against the GitHub REST API; the audit reads the checker’s JSON | Fixed |
| 4 | In Kiro Web, the DuckDB MCP path and our Playwright server don’t apply (Playwright is built into the sandbox) | Kickoff and agents fall back to DuckDB-in-Python; the setup guide explains | Fixed |
| 5 | The `github-channel` MCP server may not pick up the secret from the repo config in the cloud | The setup guide shows how to add it in Kiro Web’s MCP settings; hooks post through Python either way | Fixed |
| 6 | Solo human hours: a 60-case answer key and 60–80 field visits were too much | 30 cases (Kiro drafts, you compute the answers); 40–50 clustered visits plus a friend rating photos | Fixed |
| 7 | Uploading through the browser can skip the `.kiro` folder | Upload check in section 1; the checker flags missing files | Fixed |
| 8 | Kiro Web needs a paid plan; your access is unconfirmed | Check is step 1; Azure fallback ready | **Open: you check** |
| 9 | Whether the new 311 system still publishes coordinates and closure text | Kickoff go/no-go | **Open: the kickoff answers it** |
| 10 | One account’s credits now fund everything | Fast model for building, strong model for reviews; fix failing branches instead of rerunning; Crew skipped | Mitigated |

**Top remaining risks:**
1. The kickoff says NO-GO on the new-system data.
2. The first overnight build misses the test town, which costs a fix day.
3. Credits run short. Check your balance after session 2.
4. Validation precision is weak. Report it honestly and narrow the claim.
5. The video slips into Thanksgiving week. Have the script drafted by Nov 25.
