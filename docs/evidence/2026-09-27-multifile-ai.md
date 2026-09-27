# Bounded multi-file local AI

Local chat now ranks source chunks using multilingual E5 similarity and
snapshot-local BM25 reciprocal ranks, with exact identifier and filename boosts.
It can recover a named function even when the dense candidate order favors a
README. All candidates come from the selected repository and immutable snapshot.
The embedded Qdrant client already performs exact search; no HNSW tuning or new
remote service was introduced.

Focused questions retain one excerpt. Flow questions select distinct files and,
when a saved analysis exists, expand through resolved dependency edges for at
most two hops. Ambiguous edges are not followed. Context is limited to four
files, 24 complete lines and 1,800 characters per file, and 6,000 characters in
total. A focused excerpt permits 48 lines. The source window keeps its original
coordinates. The index version changed so earlier truncated chunks are rebuilt.

Repository-review purpose explanations receive the README and up to two code
modules; module explanations receive up to two resolved neighbors across at most
two dependency hops, so a wrapper can include its callee's storage dependency. This is
bounded evidence, not a whole-repository model review. Reanalysis is required to
regenerate an existing saved review. The chat interface exposes the source
excerpts supplied to the model, separately from the passages it actually cited.

The local Qwen worker accepts one to three passage IDs per claim. Quotes and
coordinates are derived by the server, then checked against the immutable source
again by the backend. Unknown/duplicate IDs, foreign evidence, changed quotes and
out-of-window coordinates are rejected. A single multi-file repair receives the
malformed selection and its validation error. Single-file prompts remain the
previous focused version: applying flow-specific instructions to those requests
caused a wrong conditional-return answer during regression testing. No repository
code is executed.

## Evaluation

The reproducible synthetic fixture is
`training/fixtures/multifile_retrieval.json`: an API delegates to a validation
service, which appends orders to an in-memory list through a repository module.
A migration note mentions PostgreSQL as future work; no database is implemented.
Run `python training/eval_local_multifile.py --output <report.json>` against the
running local app with AI ready. It creates a labelled fixture repository.
An optional `--repository-id` reuses that fixture. It checks response status,
required cited-file coverage, source identity and exact quotes; review the answer
text separately for meaning.

Before this change, both English and Turkish flow questions returned
`no_evidence`. The focused return-value question answered, and the nonexistent
PostgreSQL-table question correctly abstained. Those are end-to-end outcomes,
not standalone retrieval-recall scores.

Final application run (pinned Qwen3-4B-Instruct-2507, NF4 CUDA, prompt v11):

| Probe | Before | After | Cited files after | Time after |
| --- | --- | --- | --- | --- |
| English three-file order flow | no_evidence | answered | api, service, repository | 20.75 s |
| Turkish three-file order flow | no_evidence | answered | api, service, repository | 27.16 s |
| Focused `save_order` return value | answered | answered | repository | 13.09 s |
| Nonexistent PostgreSQL table | no_evidence | no_evidence | none | 5.22 s |

All four status/coverage/quote checks passed. Manual reading confirmed the
import-and-call flow, the `quantity <= 0` boundary in Turkish, and list insertion;
the English persistence-wording caveat below remains. These small timings are
single local observations, not latency guarantees.

A follow-up question without filenames traced `submit_order` through the saved
graph and cited API, service and repository sources, correctly describing the
nonpositive-quantity rejection and in-memory list insertion. Regenerating the
synthetic repository review produced a project explanation and all three module
explanations. Adding the second dependency hop and naming the primary file in
each question corrected an observed invented return meaning: the API explanation
now identifies `len(orders)` as the count after insertion. The review asks about
demonstrated operations, avoiding an unsupported inferred audience or CRUD API.

Verification on 2026-09-27: 365 backend tests passed, 37 PostgreSQL-dependent
tests skipped; 77 frontend tests, TypeScript and production build passed; 15
worker unit tests passed. The existing 18-case real-model single-source suite
also passed with the final v11 worker, including conditional values, unsupported
features and source-instruction attacks. Earlier experimental flow prompts
regressed that suite and were not retained for single-source requests. Existing
Starlette deprecation and Mermaid bundle-size warnings remain.

The browser also queried the real PyPA `sampleproject` snapshot
`621e4974ca25ce531773def586ba3ed8e736b3fc`: it connected
`tests/test_simple.py` to `src/sample/simple.py` and correctly explained
`self.assertEqual(add_one(5), 6)`, citing both files. The Turkish context-list
control expanded by keyboard and its source link opened the pinned test file.
At a 390-pixel viewport the DOM reported no horizontal document overflow; the
temporary viewport override was reset afterward.

## Boundaries

Exact quote checks do not establish that every claim follows from its citations.
A filename-only citation rule was tested and discarded: an import-and-call
statement can be supported by the caller's source without citing the callee's
definition. Such a rule rejected valid relationships while still failing to
prove semantics. The model is instructed to cite supporting passages, but manual
review remains necessary, especially for claims of persistence, reachability or
runtime behavior. In the small flow probe, English wording about storing an order
was less precise than explicitly saying “in memory.”

Intent detection and ranking are bounded heuristics, not calibrated confidence.
Four excerpts can omit needed code; long files, ambiguous basenames, unsupported
relationships and flows beyond two graph hops need broader evaluation. Saved
graphs retain their original parser limitations. PostgreSQL-dependent skipped
tests do not establish hosted-server readiness.
