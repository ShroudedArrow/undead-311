# Kiro log

**Version note:** Surface: Kiro Web. Date: 2026-11-12. No version number is shown, so none is recorded.

**Counts:** specs 0 · steering docs 14 · hooks 0 · custom agents 0 · workflows 0 · MCP servers 5 · property tests 6 · powers 0

Format: `YYYY-MM-DD | surface | feature | what was built/fixed | issue + fix`

2026-11-12 | Kiro Web | kickoff (prompts/00-kickoff.md) | Downloaded 2015-present 311 CSVs (legacy + new system), loaded DuckDB, recorded go/no-go (GO) in docs/DECISIONS.md, proposed in-scope types, updated data-dictionary.md, built data/sample (21,733 rows), added Makefile/.python-version/.nvmrc/lock files | MCP servers not exposed in this session (used Python/DuckDB directly); S3 redirects with an explicit :443 returned 403 in urllib, fixed in download.py by stripping :443; /tmp does not persist so scratch scripts live in .local-data/scratch
2026-11-12 | Kiro Web | steering + PBT (hypothesis) | Narrowed scope, added mirror/transfer rules and step 6 source_unknown, UTC+local time normalization, rebuilt sample (15,603 rows), DST property test, docs corrections | The kickoff run mislabeled new-system timestamps as UTC and its sample had times shifted 4 or 5 h; fixed using evidence from 1,373 BCS resubmission pairs (new open minus legacy close about -2.6 min in every month)
