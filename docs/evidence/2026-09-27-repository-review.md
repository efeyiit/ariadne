# Repository review and interface languages — 27 September 2026

The local Overview now combines repository purpose, entry-point candidates,
module responsibilities, prioritized rule findings, a dependency diagram, test
observations, source links, and analysis scope. Explicit reanalysis creates a new
report while preserving prior results; concurrent requests still share active work.
English is the default interface language. Turkish can be selected in the header;
the preference persists locally and updates the document language. New explanation
requests use the selected language. Existing reports retain their original language
and show a regeneration notice when it differs from the interface. Code, file names,
source quotations and original analyzer details are preserved.

## Evidence

- Backend suite: **346 passed, 37 skipped** (PostgreSQL prerequisites). One existing
  Starlette deprecation warning. Tests cover forced reanalysis, source identity,
  invalid citations, model failure, cancellation, priority filtering, language,
  simple-expression explanations and coverage artifact propagation.
- Frontend suite: **73 passed**; TypeScript and production build passed. The build
  retains the existing large lazy Mermaid chunk warning.
- Real local Qwen3-4B model plus browser: English and Turkish `sampleproject` reviews
  were generated; language preference survived reload, report IDs changed, a Mermaid
  diagram rendered, and the 390-pixel viewport had no horizontal overflow. No browser
  page or console errors were observed in that run.
- Manual answer review caught contradictory Turkish arithmetic in a generated module
  explanation. The final code explains supported simple Python return/print shapes
  directly from AST without running source or asking the model. Regression tests
  verify `number + 1` and printing a placeholder rather than executing its text.
- Test fixture numeric literals remain in raw Findings but are omitted from priority
  recommendations. Application modules are preferred over test/tooling files for AI
  explanation. A supplied root `coverage.xml` reaches the testing analyzer; absent
  coverage is never synthesized. Cancelled queued work no longer prepares sources.

## Remaining verification and limits

The last full browser/model run preceded the final AST and priority refinements.
Their unit checks passed, but restarting the running service to validate the final
combined build was blocked by the execution environment. That final restart and
browser acceptance remain pending; this is not a fully closed live acceptance.

AI explanations are bounded to project purpose, up to three application modules
and two priority findings, with at most 48 source lines per request. Static analysis
still covers the supported imported files. Other module declarations, full findings
and dependency details remain available in the report. Model output can still be
wrong; exact source matching does not prove semantic entailment. Entry-point and
architecture observations are source candidates, not executed runtime traces.
Unverified AI explanations are unavailable/rejected explicitly. The analyzer does
not run imported code or tests, and no account or cloud inference is required.
