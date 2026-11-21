# Validation

<!-- coroner-random:start -->
## Coroner accuracy on a random draw of full-data closures

200 closed in-scope cases drawn at random (seed 311) and labeled by the Coroner agent (`data/labels/coroner_random200.csv`). The label table, the closure code and the leading-phrase rule are applied as in the pipeline.

- Agreement: 92.0% (184 of 200), Wilson 95% interval 87.4% to 95.0%.
- Left unlabeled (`other`): 0.

| label source | cases | agree |
|---|---|---|
| code | 2 | 0 |
| phrase | 70 | 58 |
| table | 128 | 126 |

Top confusions (Coroner label, pipeline label, cases):

| Coroner | pipeline | cases |
|---|---|---|
| referred | noted | 3 |
| noted | resolved | 2 |
| resolved | referred | 2 |
| duplicate | referred | 1 |
| invalid | noted | 1 |
| made_safe_temporary | referred | 1 |
| noted | invalid | 1 |
| noted | planned_followup | 1 |
| planned_followup | noted | 1 |
| planned_followup | resolved | 1 |
<!-- coroner-random:end -->

<!-- records-validation:start -->
## Records-based check of the validation sample

No field visits were made. The 50 sampled possible zombies (`data/labels/validation_sample.csv`, seed 311) were checked against the city's records on 2026-11-21: how was each re-report closed? This measures what crews recorded, not what is on the street, and a closure recorded as a repair can still be wrong. One reader classified the closures by rule, so there is no inter-rater agreement.

- Repaired again, not ambiguous: 20.0% (10 of 50), Wilson 95% interval 11.2% to 33.0%.
- Range if ambiguous repairs also count: up to 42.0% (21 of 50), Wilson 95% interval 29.4% to 55.8%.
- Among re-reports already closed: 25.6% (10 of 39), Wilson 95% interval 14.6% to 41.1%.

| class | cases | of which ambiguous |
|---|---|---|
| repaired again | 21 | 11 |
| duplicate | 2 | 0 |
| invalid or nothing found | 4 | 0 |
| referred | 2 | 0 |
| still open | 11 | 0 |
| other | 10 | 10 |

Repaired again by case type (small groups, wide intervals):

| case type | cases | repaired again | share, 95% interval |
|---|---|---|---|
| pothole roadway | 23 | 1 | 4.3% (0.8% to 21.0%) |
| sidewalk | 5 | 0 | 0.0% (0.0% to 43.4%) |
| sign | 4 | 0 | 0.0% (0.0% to 49.0%) |
| streetlight | 18 | 9 | 50.0% (29.0% to 71.0%) |

Ambiguous cases (21), listed apart and left out of the main figure:

| zombie | type | class | reason |
|---|---|---|---|
| 101006697934:BCS-00363178 | sign | other | unlabeled |
| BCS-00261305:BCS-00343428 | streetlight | other | unlabeled |
| BCS-00280351:BCS-00345642 | pothole roadway | repaired again | conflicting cue |
| BCS-00284775:BCS-00357056 | streetlight | other | unlabeled |
| BCS-00305005:BCS-00360230 | pothole roadway | repaired again | conflicting cue |
| BCS-00331359:BCS-00333825 | pothole roadway | repaired again | conflicting cue |
| BCS-00333583:BCS-00352799 | pothole roadway | other | unlabeled |
| BCS-00333825:BCS-00337048 | pothole roadway | repaired again | conflicting cue |
| BCS-00336431:BCS-00345953 | pothole roadway | other | unlabeled |
| BCS-00337048:BCS-00339545 | pothole roadway | repaired again | conflicting cue |
| BCS-00340144:BCS-00355515 | sidewalk | repaired again | conflicting cue |
| BCS-00341732:BCS-00352179 | pothole roadway | repaired again | conflicting cue |
| BCS-00344269:BCS-00373240 | pothole roadway | repaired again | conflicting cue |
| BCS-00345716:BCS-00361824 | pothole roadway | other | unlabeled |
| BCS-00346623:BCS-00353186 | pothole roadway | other | unlabeled |
| BCS-00346824:BCS-00358596 | pothole roadway | repaired again | conflicting cue |
| BCS-00353029:BCS-00363452 | pothole roadway | other | unlabeled |
| BCS-00353512:BCS-00355286 | pothole roadway | other | unlabeled |
| BCS-00360877:BCS-00371707 | pothole roadway | repaired again | conflicting cue |
| BCS-00379734:BCS-00380837 | sidewalk | repaired again | conflicting cue |
| BCS-00382363:BCS-00385544 | streetlight | other | unlabeled |

Record-confirmed zombies (repaired again, not ambiguous): 10.
<!-- records-validation:end -->
