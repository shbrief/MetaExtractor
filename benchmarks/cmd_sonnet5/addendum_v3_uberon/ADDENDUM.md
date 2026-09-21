# Scoring-only addendum on `out_v3`

Median [min-max] over three repeats. No re-extraction: the same saved model
responses are re-scored, with the fan-out replayed under the current schema.

| stage | model | all-curated P | all-curated R | all-curated F1 | matched F1 |
|---|---|---|---|---|---|
| out_v3 as published | Sonnet 5 | 0.739 [0.637-0.739] | 0.118 [0.105-0.126] | 0.203 [0.180-0.216] | 0.514 [0.452-0.538] |
| out_v3 as published | Haiku 4.5 | 0.657 [0.601-0.691] | 0.108 [0.083-0.115] | 0.186 [0.148-0.193] | 0.468 [0.467-0.475] |
| + TettAJ gold union | Sonnet 5 | 0.691 [0.602-0.694] | 0.121 [0.105-0.128] | 0.205 [0.178-0.217] | 0.494 [0.430-0.515] |
| + TettAJ gold union | Haiku 4.5 | 0.629 [0.575-0.640] | 0.108 [0.082-0.114] | 0.184 [0.146-0.190] | 0.445 [0.435-0.445] |
| + current fan-out rules | Sonnet 5 | 0.690 [0.601-0.715] | 0.102 [0.092-0.113] | 0.178 [0.160-0.195] | 0.442 [0.395-0.479] |
| + current fan-out rules | Haiku 4.5 | 0.623 [0.608-0.625] | 0.089 [0.076-0.095] | 0.156 [0.136-0.165] | 0.405 [0.391-0.410] |
| + threshold 0.8 | Sonnet 5 | 0.690 [0.601-0.715] | 0.102 [0.092-0.113] | 0.178 [0.160-0.195] | 0.442 [0.395-0.479] |
| + threshold 0.8 | Haiku 4.5 | 0.623 [0.608-0.625] | 0.089 [0.076-0.095] | 0.156 [0.136-0.165] | 0.405 [0.391-0.410] |
| + custom-enum crosswalks | Sonnet 5 | 0.752 [0.681-0.773] | 0.111 [0.105-0.122] | 0.194 [0.181-0.210] | 0.482 [0.448-0.518] |
| + custom-enum crosswalks | Haiku 4.5 | 0.668 [0.666-0.689] | 0.098 [0.082-0.104] | 0.172 [0.146-0.180] | 0.439 [0.432-0.444] |

## Notes

**Fan-out.** Replaying the current rules over the saved records rewrites 131801 propagated cells as 91199. The reduction is not the
heterogeneity sentinel: the seven slots that were unannotated when `out_v3` ran are
now `scope: sample`, which subjects them to both the propagation allowlist and the
subgroup gate, and `uncurated_metadata` became sample-scoped after `bench-v3`. So
this stage measures every fan-out annotation change since that tag, not only the
sentinel. Block reasons under the current rules: `blocked_aggregate` 210, `blocked_heterogeneous` 896, `blocked_multi_valued` 64041, `blocked_sample_scope` 22264, `blocked_sample_scope_no_propagation` 41801, `blocked_subgroup_value` 3, `blocked_unit_without_value` 10784.

**The sentinel fires but never decides.** It blocks 896 cells, yet forcing
`sample_rules.is_heterogeneous` to `False` reproduces this stage exactly, and not one
sample cell differs. The gate sits ahead of the allowlist and subgroup checks, so every
value it blocks would have been blocked by one of those anyway: the only study reporting
cohort variety (`PasolliE_2019`: `Mixed`, `Multiple countries`, `Multiple ancestries`)
declares subgroups, which stops a sample-scoped value on its own. The gate is therefore
a guard for a case these ten studies do not contain -- a cohort-variety value on an
allowlisted field in a study that declares no subgroups -- and it currently changes the
reason a cell is withheld, not whether it is.
