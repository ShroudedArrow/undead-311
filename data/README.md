# Data

- Raw and processed data live outside git tracking: $DATA_DIR outside the repo on local or Azure runs; the gitignored .local-data/ folder in Kiro Web (default `~/undead311-data/` locally): `raw/` (downloaded Boston 311 CSVs) and `processed/` (DuckDB + Parquet).
- `sample/` — small committed sample for tests and judge mode.
- `labels/` — coroner_labels.csv and the hand-checked validation sample.
- `SNAPSHOT.md` — download date, file list, and hashes for the judging snapshot.

Source: Analyze Boston "311 Service Requests". License: Open Data Commons PDDL.

Resource list (filled in by the kickoff session):

Dataset: 311 Service Requests (`311-service-requests`), https://data.boston.gov/dataset/311-service-requests . Listed via CKAN `package_show` on 2026-11-12 (dataset metadata_modified 2026-11-12T14:49:25).

| resource | format | URL | last modified |
|---|---|---|---|
| 311 Service Requests - NEW SYSTEM | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/254adca6-64ab-4c5c-9fc0-a6da622be185/download/tmpbt_i3dsl.csv | 2026-11-11T17:41:09 |
| (unnamed documentation) | PDF | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/6e443a5d-8027-41d5-9574-35e8f84b8284/download/311-service-requests-data-dictionary-new-system.pdf | n/a |
| (unnamed documentation) | PDF | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/b237f352-49d1-4423-804f-b478e4f24e61/download/datadictionary-crmvaluecodeindex.pdf | 2017-04-06T15:56:15 |
| (unnamed documentation) | link | https://docs.google.com/document/d/e/2PACX-1vRwAs48Ou0txiw1NPudex752jfa34MvoBwlT2WlTf_aTVLcIsXsV4Pzdm4xBrEeYMszrUZyN-IRZG2_/pub | n/a |
| (unnamed documentation) | link | https://docs.google.com/document/d/e/2PACX-1vQ9ExKIGyrLJeyVUO92qNw0Cbj5m6Sz2IAATdBgYiAGW69Wuv7dk10PHUPR7UdawGt_e89q9VhxH-I0/pub | n/a |
| 311 Service Requests - 2026 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/1a0b420d-99f1-4887-9851-990b2a5a6e17/download/tmpiofpxmk5.csv | 2026-11-12T14:49:25 |
| 311 Service Requests - 2025 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/9d7c2214-4709-478a-a2e8-fb2020a5bb94/download/lagan_311_open_data_2025_rvsd3.csv | 2026-09-18T01:27:22 |
| 311 Service Requests - 2024 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/dff4d804-5031-443a-8409-8344efd0e5c8/download/lagan_311_open_data_2024_rvsd3.csv | 2026-09-18T01:27:27 |
| 311 Service Requests - 2023 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/e6013a93-1321-4f2a-bf91-8d8a02f1e62f/download/lagan_311_open_data_2023_rvsd3.csv | 2026-09-18T01:27:26 |
| 311 SERVICE REQUESTS - 2022 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/81a7b022-f8fc-4da5-80e4-b160058ca207/download/lagan_311_open_data_2022_rvsd3.csv | 2026-09-18T01:26:58 |
| 311 SERVICE REQUESTS - 2021 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/f53ebccd-bc61-49f9-83db-625f209c95f5/download/lagan_311_open_data_2021_rvsd3.csv | 2026-09-18T01:26:42 |
| 311 SERVICE REQUESTS - 2020 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/6ff6a6fd-3141-4440-a880-6f60a37fe789/download/lagan_311_open_data_2020_rvsd3.csv | 2026-09-18T01:25:57 |
| 311 SERVICE REQUESTS - 2019 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/ea2e4696-4a2d-429c-9807-d02eb92e0222/download/lagan_311_open_data_2019_rvsd3.csv | 2026-09-18T01:25:43 |
| 311 SERVICE REQUESTS - 2018 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/2be28d90-3a90-4af1-a3f6-f28c1e25880a/download/lagan_311_open_data_2018_rvsd3.csv | 2026-09-18T01:25:25 |
| 311 SERVICE REQUESTS - 2017 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/30022137-709d-465e-baae-ca155b51927d/download/lagan_311_open_data_2017_rvsd3.csv | 2026-09-18T01:24:36 |
| 311 SERVICE REQUESTS - 2016 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/b7ea6b1b-3ca4-4c5b-9713-6dc1db52379a/download/lagan_311_open_data_2016_rvsd3.csv | 2026-09-18T01:22:47 |
| 311 SERVICE REQUESTS - 2015 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/c9509ab4-6f6d-4b97-979a-0cf2a10c922b/download/lagan_311_open_data_2015_rvsd3.csv | 2026-09-18T01:22:34 |
| 311 SERVICE REQUESTS - 2014 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/bdae89c8-d4ce-40e9-a6e1-a5203953a2e0/download/lagan_311_open_data_2014_rvsd3.csv | 2026-09-18T01:22:08 |
| 311 SERVICE REQUESTS - 2013 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/407c5cd0-f764-4a41-adf8-054ff535049e/download/lagan_311_open_data_2013_rvsd3.csv | 2026-09-18T01:21:54 |
| 311 SERVICE REQUESTS - 2012 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/382e10d9-1864-40ba-bef6-4eea3c75463c/download/lagan_311_open_data_2012_rvsd3.csv | 2026-09-18T01:21:30 |
| 311 SERVICE REQUESTS - 2011 | CSV | https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource/94b499d9-712a-4d2a-b790-7ceec5c9c4b1/download/lagan_311_open_data_2011_rvsd3.csv | 2026-09-18T01:21:10 |

Notes:
- Yearly legacy-system files are named `311 Service Requests - YYYY` (2011-2026). The 2026 file is still growing (about 190k rows through Nov 10, 2026), so legacy-system cases continue after the Oct 2025 switch.
- The NEW SYSTEM file starts at 2025-08-01 (not Oct 2025), is much smaller (87,951 rows) and grows quickly from mid-2026.
- The kickoff downloader (`pipeline/scripts/download.py`) fetches 2015 onward plus the new-system file into `$DATA_DIR/raw/`; hashes are in `SNAPSHOT.md`.
