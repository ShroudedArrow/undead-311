# Validation

<!-- coroner-random:start -->
## Coroner accuracy on a random draw of full-data closures

200 closed in-scope cases drawn at random (seed 311) and labeled by the Coroner agent (`data/labels/coroner_random200.csv`). The label table, the closure code and the leading-phrase rule are applied as in the pipeline.

- Agreement: 90.0% (180 of 200), Wilson 95% interval 85.1% to 93.4%.
- Left unlabeled (`other`): 0.

| label source | cases | agree |
|---|---|---|
| code | 2 | 0 |
| phrase | 72 | 56 |
| table | 126 | 124 |

Top confusions (Coroner label, pipeline label, cases):

| Coroner | pipeline | cases |
|---|---|---|
| invalid | noted | 3 |
| noted | resolved | 3 |
| referred | noted | 3 |
| resolved | referred | 2 |
| duplicate | referred | 1 |
| invalid | resolved | 1 |
| made_safe_temporary | referred | 1 |
| noted | planned_followup | 1 |
| planned_followup | noted | 1 |
| planned_followup | resolved | 1 |
<!-- coroner-random:end -->
