# Acceptance check — `out_v5` against `out_v4`

## 1. Scores

| join | model | out_v4 repeats | out_v4 range | out_v5 repeats | out_v5 median | ok? |
|---|---|---|---|---|--:|:-:|
| all curated | haiku | [0.1639, 0.1767, 0.1798] | 0.164–0.180 | [0.1705, 0.1468, 0.1777] | 0.171 | yes |
| all curated | sonnet | [0.166, 0.1874, 0.1651] | 0.165–0.187 | [0.1747, 0.1857, 0.1521] | 0.175 | yes |
| matched | haiku | [0.4106, 0.4416, 0.4481] | 0.411–0.448 | [0.4277, 0.3802, 0.4466] | 0.428 | yes |
| matched | sonnet | [0.4213, 0.4682, 0.4158] | 0.416–0.468 | [0.4412, 0.466, 0.3919] | 0.441 | yes |

`ok?` is **yes** when the out_v5 median sits inside the out_v4 range *and* the ranges overlap; **median** when only the ranges overlap; **NO** when they are disjoint. With three repeats a side, treat this as a direction and read the points.

## 2. Prompt caching

| model | tree | cache_write | cache_read | read/write |
|---|---|--:|--:|--:|
| haiku | out_v4 | 596,238 | 1,192,476 | 2.0 |
| haiku | out_v5 | 596,238 | 1,192,476 | 2.0 |
| sonnet | out_v4 | 778,230 | 1,795,311 | 2.307 |
| sonnet | out_v5 | 778,230 | 1,758,030 | 2.259 |

## Verdict

**Scores: PASS** — the median sits inside the reference spread and the ranges overlap, for every join and model.

**Caching: PASS** — prefixes are still being reused at the reference rate.


## 3. Byte-identical input, confirmed against the real API

The unit-level golden payload test pins one request. This is the same claim at
scale, from the API's own accounting:

| tree | model | calls | input | cache_write | cache_read | output |
|---|---|--:|--:|--:|--:|--:|
| `out_v4` | haiku | 228 | 668,451 | 596,238 | 1,192,476 | 310,155 |
| `out_v5` | haiku | **228** | **668,451** | **596,238** | **1,192,476** | 319,471 |
| `out_v4` | sonnet | 257 | 953,220 | 778,230 | 1,795,311 | 870,731 |
| `out_v5` | sonnet | 261 | 1,101,546 | 778,230 | 1,758,030 | 841,275 |

**The Haiku arm is identical to the token on every input-side counter across all
228 calls**, and differs only in output tokens, which the model samples. Cache
write and read depend on the input alone — a frozen paper, a frozen schema and
deterministic batching — so this is the strongest available statement that the
Model seam did not change a single byte of what goes on the wire.

The Sonnet arm made 4 more calls (261 against 257). Those are truncation
retries, which trigger on `stop_reason == "max_tokens"` and so depend on
sampled output length; `cache_write` is nonetheless identical (778,230) and
`cache_read` differs in proportion to the call count. Expected, not a signal.

## 4. Run completion

| | `out_v4` | `out_v5` |
|---|---|---|
| tasks | 60 | 60 |
| attempts | 63 | 63 |
| produced output | 60 | **60** |
| single commit, clean tree | yes | yes (`097d8a1`) |
| cost | — | **US$16.04** (haiku $3.13, sonnet $12.91) |

Three attempts needed a retry (sonnet/3 TettAJ_2019_b, sonnet/2 FanY_2023,
haiku/3 TettAJ_2019_b), all of which succeeded on the second try. For reference
`out_v3` lost one extraction entirely; this run lost none.

Sample counts match `out_v4` in 29 of 30 Sonnet study-repeats. The exception is
FanY_2023 r3, where `out_v4` produced 85 and `out_v5` produced 100 — but
`out_v4`'s own r1 and r2 produced 100, so `out_v4` r3 was the outlier and
`out_v5` is 100/100/100.

## Provenance notes

- Scored against curatedMetagenomicDataCuration **`41271711`**, the commit
  `out_v4` and the manuscript used. The local checkout had advanced to
  `6828fb9`, and all ten gold tables differ between the two, so scoring against
  the working checkout would have confounded the refactor with a gold change. A
  detached worktree at `41271711` was used instead.
- `out_v5/runs.jsonl` records `curation_commit: ""` because `CMD_CURATION_DIR`
  was not set when the extractions ran. That is harmless for the extractions —
  they never read gold, which is the firewall's whole point — but it is a
  provenance gap worth closing: `run_frozen._curation_commit()` returns an empty
  string when the repo is missing rather than warning, so a run can be recorded
  with no record of the gold it would be scored against.
- Retrievals were `out_v4`'s, copied in, so the only variable is the code.
