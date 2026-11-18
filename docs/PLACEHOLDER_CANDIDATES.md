# Placeholder candidates (report only, nothing excluded)

Source: `cases_clean` after load, normalize, crosswalk and clean on the raw files downloaded 2026-11-18 (the same files as rehearsal-1: `311_2026.csv` and `311_new_system.csv` changed on 2026-11-17, the rest equal the committed table). `cases_clean` has 388,654 rows. A candidate is a coordinate, rounded to 4 decimals, shared by more than 200 in-scope cases (`PLACEHOLDER_CANDIDATE_MIN` in `ingest/clean.py`). Three points qualify. The exclusion rule in `zombie-definition.md` step 1 still lists only the two points 42.3603,-71.0583 and 42.3595,-71.0588; this file changes nothing there.

| point (lat, lon) | cases | systems | distinct addresses | distinct case types | distinct families | top case type |
|---|---|---|---|---|---|---|
| 42.3475, -71.0686 | 224 | 222 legacy, 2 new | 2 | 12 | 6 | Request for Pothole Repair, 130 |
| 42.3906, -70.9964 | 224 | 224 legacy | 2 | 6 | 5 | Request for Pothole Repair, 195 |
| 42.3832, -71.0393 | 207 | 205 legacy, 2 new | 3 | 11 | 4 | Request for Pothole Repair, 184 |

"Distinct addresses" counts distinct values of the normalized `street` field; "distinct case types" counts distinct `type_raw` values.

Address strings at each point (all of them, since fewer than five exist):

- 42.3475, -71.0686 (Downtown / Financial District, 222 cases; South End, 2): `INTERSECTION Arlington St & Herald St` (222), `Tremont St` (2).
- 42.3906, -70.9964 (East Boston, 224): `INTERSECTION Leverett St & Bennington St` (222), `INTERSECTION Bennington St & Leverett St` (2). The two strings name the same intersection.
- 42.3832, -71.0393 (East Boston, 207): `INTERSECTION Nay St & Andrew P McArdle Brg` (202), `INTERSECTION Meridian St & Nay St` (3), `Meridian St` (2). McArdle is the name of a public bridge.

What the numbers show, without a decision attached: at each point 99% or more of the cases (222 of 224, 222 of 224, 202 of 207) carry the same intersection address string, and one pothole type dominates. All three points are an intersection's default coordinate, which is how a case with only an intersection name would be located. The cases span 2015 to 2026 and mix city-originated and resident sources (for example 81 Employee Generated and 129 Citizens Connect App at the first point), so they are many separate reports, not one repeated record.

Open question for the owner: whether to add these three points to ZD step 1 and log it in the change log with a date, before the Friday snapshot. Not done.
