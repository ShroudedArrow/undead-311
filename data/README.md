# Data

- Raw and processed data live outside git tracking: $DATA_DIR outside the repo on local or Azure runs; the gitignored .local-data/ folder in Kiro Web (default `~/undead311-data/` locally): `raw/` (downloaded Boston 311 CSVs) and `processed/` (DuckDB + Parquet).
- `sample/` — small committed sample for tests and judge mode.
- `labels/` — coroner_labels.csv and the hand-checked validation sample.
- `SNAPSHOT.md` — download date, file list, and hashes for the judging snapshot.

Source: Analyze Boston "311 Service Requests". License: Open Data Commons PDDL.

Resource list (filled in by the kickoff session):
