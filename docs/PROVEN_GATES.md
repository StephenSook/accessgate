# Which gates are proven to fail

A green check mark proves a suite ran. It does not prove the suite would have
caught anything. Those are different claims, and only the second one is worth
anything to a reader.

Every invariant listed here was verified the same way: break it deliberately,
confirm the suite goes red, restore. A test that has never been observed failing
is a hypothesis.

This file exists because two findings in this project were exactly that failure
mode, one in a rival and one here:

- A rival's CI documents that a self-skipping test hid a broken ingest path for
  four weeks. Their suite was green throughout.
- Our own built-bundle secret scan had **never executed in CI**. The job that ran
  pytest never built the frontend, so the scan skipped every time while reporting
  green. Its own docstring called that acceptable. Fixed in `a502d33`, and the
  CI log now shows those two tests as `PASSED` rather than `SKIPPED`.

## Mutation log

Each row is a change that was actually applied to a working tree, run, and
reverted. "Caught by" names the assertion that failed.

| Invariant | Mutation applied | Caught by |
|---|---|---|
| A work quantity cannot be zeroed | `FINDINGS_IN_BRIEF = 0` | `test_no_work_quantity_is_zero` |
| No mock/disable switch at module scope | added `MOCK_EMBEDDINGS = True` | `test_no_kill_switch_constant_exists` |
| Generative acceptance needs every conjunct | removed `guardian_ran` from the gate | `test_the_generative_gate_still_requires_every_check` |
| A citation may not be a search query | set a `clause_url` to a Google Scholar query | `test_no_citation_points_at_a_search_engine` |
| A measurement cannot exist without its limit | set `measured` with `limit = None` | `test_absent_measurements_are_null_rather_than_defaulted` |
| Production API base may not be absolute | hardcoded a foreign `vercel.app` origin | `test_the_production_api_base_names_no_foreign_domain` |
| Citations must be verbatim from the corpus | (verified non-vacuous: 9 of 9 present in 222 chunks) | `test_every_citation_is_verbatim_from_the_corpus` |
| The citation path may never generate | added a `/ml/v1/text/chat` constant to `rag.py` | `test_the_citation_path_embeds_but_never_generates` |
| `/judges` must state the retrieval-not-opinion rule | deleted the sentence | `test_judges_states_the_distinction` |
| Every imported module must be declared | dropped `requests`, then `transformers` | `test_every_module_src_imports_directly_is_declared` |
| No foreign model provider in the engine | smuggled `import openai`, then a Groq endpoint | `test_the_engine_calls_no_provider_but_ibm` |
| Every engine module must be reachable | made `engine.py` unimported | `test_every_engine_module_is_reachable_from_application_code` |
| The offline classifier must stay disclosed | deleted the disclosure; redrew the `CLS --> NER` edge | `test_an_exempted_module_is_disclosed_as_offline_in_the_readme` |
| Disclosures must reach the card | stripped the `unsupported_figures` render | `test_every_disclosure_field_is_referenced_by_the_summary_card` |
| The bundle scan may not skip in CI | removed `frontend/dist` with `CI=true` | `_require_bundle` |

## Non-vacuity guards

Several checks iterate a fixture or a regex match set. If the fixture emptied or
the pattern stopped matching, the assertion would pass over nothing and still
report green, which is worse than no check because it wears the credibility of
one. Each of those has a companion test asserting the input set is non-empty:

`test_the_truth_set_is_not_empty`, `test_the_import_scan_is_not_vacuous`,
`test_the_constant_scan_is_not_vacuous`, `test_the_fixture_is_not_vacuous`,
`test_the_corpus_is_present_and_substantial`,
`test_the_foreign_provider_pattern_still_matches_something`.

Each of these was itself mutation-tested by neutering its scanner and confirming
the guard fired.

## What this file does not claim

It does not claim the suite is complete, or that every invariant in the project
is pinned. It claims only that the rows above were observed failing when broken,
on the dates the corresponding commits landed. Anything not listed here has not
been proven, and should be read that way.
