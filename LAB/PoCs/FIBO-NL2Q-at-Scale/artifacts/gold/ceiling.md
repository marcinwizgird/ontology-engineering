# Compiler ceiling on FIBEN

Accepted = reproduces the gold rows on the base data and on all five variants (V1-V4 perturbed, V5 witness).

| query type | n | translated | compiled & ran | **match (ceiling)** | match on non-empty gold |
|---|---|---|---|---|---|
| non-nested | 106 | 105 | 103 | **100** (94%) | 64/70 |
| type-a | 45 | 45 | 45 | **43** (96%) | 25/27 |
| type-j | 27 | 27 | 27 | **24** (89%) | 10/12 |
| type-ja | 31 | 30 | 28 | **25** (81%) | 7/10 |
| type-n | 28 | 28 | 27 | **27** (96%) | 22/22 |
| **all** | 237 | 235 | 230 | **219** (92%) | 128/141 |

Failure causes:

* 5 x compare: 
* 2 x finish: unsupported term function 'COALESCE2' (DefaultDBCoalesceFunc
* 2 x compare: a gold column has no equal prediction column
* 2 x translate: Unsupported
* 2 x compare: both empty
* 2 x reformulate: Ontop could not push this query into a single SQL statement 
* 1 x reformulate: OntopUnsupportedInputQueryException
* 1 x compare: row count 0 != 13
* 1 x compare: row count 6 != 2
