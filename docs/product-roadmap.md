# Product roadmap

**Current state (2026-09-27):** The account-free local workspace imports public GitHub repositories and local source folders, saves immutable snapshots and reports in SQLite, runs static analysis, and links findings back to saved source lines. It includes a source-backed project review, architecture, dependencies, findings, security, testing, refactoring, documentation, and optional local AI chat. English is the default; Turkish can be selected and persists. Explicit reanalysis preserves earlier results. See the [repository review acceptance](evidence/2026-09-27-repository-review.md), [dependency correction](evidence/2026-09-27-python-src-dependencies.md), and [local diagram selection](evidence/2026-09-27-local-diagram-selection.md) for evidence and limits.

## Capability areas and remaining work

These areas describe the full intended scope. Some are implemented in the local workspace; this list does not claim that every item is complete.

1. **Repository intake and identity:** public GitHub import and local/private source-folder import are available without login. Public snapshots retain a full commit SHA; local snapshots use a content identity. Hosted private GitHub access remains part of the separate authenticated-server work.
2. **Code structure:** parse Python, TypeScript, Java, C#, and C++; build symbol, module, and dependency relationships; detect cycles and infer architecture from traceable evidence.
3. **Analysis outputs:** generate dependency and UML views; identify code smells, SOLID concerns, refactoring opportunities, test gaps, and security risks; propose tests, README text, API documentation, and technical-debt summaries.
4. **Source-linked assistance:** optional local chat currently answers from one highest-ranked source excerpt, with source-line and quote validation. The repository review now includes bounded project/module explanations and prioritized actions. Broad and multi-file reasoning and wider-context retrieval remain limited. Simple Python return/print explanations use AST evidence; arbitrary model interpretations still require review. Rule-based findings stay separate from AI interpretations.
5. **Application and scale:** persist analyses, run jobs asynchronously, cache by branch and commit, expose report APIs, and present findings, diagrams, tests, security, documentation, and chat in the web interface.
6. **Change tracking and delivery:** support incremental analysis, pull-request diffs and webhooks, issue drafts with an explicit publish action, architecture history, containerized operation, CI, evaluation, and an end-to-end demo.

## Remaining local-product work

- Connect the existing test-design generator to a usable local report/authoring flow; its presence as a module is not end-to-end delivery.
- Improve multi-file retrieval and explanation quality, evaluated against representative repositories and questions with known answers.
- Expose analysis history and comparisons, then verify incremental updates without stale source references or findings.
- Complete and verify the intended pull-request/issue workflows separately from the account-free local path.
- Broaden real-repository acceptance, failure/recovery checks and the reproducible demonstration. PostgreSQL-dependent skipped tests do not establish hosted-server readiness.

The local architecture view now selects class, static-call and component diagrams,
previews Mermaid locally, and downloads Mermaid or PlantUML source for the exact
selected analysis. PlantUML image rendering is not provided by the local UI.

## Verification boundaries

Analyzed repository content is data, not instructions. Running that code is outside the default analysis path. Test discovery and measured coverage are different results; coverage requires an existing coverage artifact. Each planned capability needs behavior tests and evidence before it is described as implemented.

The [source design](source-design.md) contains the full intended scope. This roadmap expresses implementation areas without narrowing that scope or claiming a release date.
