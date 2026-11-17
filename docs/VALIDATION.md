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
