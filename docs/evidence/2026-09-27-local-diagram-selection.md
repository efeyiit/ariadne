# Local architecture diagram selection

The local Architecture view now offers file/component, class and static-call
diagrams. Mermaid renders in the existing script-free sandbox; Mermaid and
PlantUML source can be inspected and downloaded without sending repository
content to a remote rendering service. Controls and explanations support English
and Turkish. PlantUML image rendering is not part of this local interface.

`GET /api/local/diagrams` requires repository, snapshot and analysis IDs. The
existing local-session boundary applies. The selected immutable analysis supplies
the dependency graph; its immutable source snapshot is parsed inertly to identify
standalone classes. No repository code is executed. Foreign analysis IDs return
409, missing reports/graphs return 404, and unsupported/oversized graphs return
422. Responses disable caching; the client validates all three identity fields
and aborts obsolete requests.

Live testing also exposed an existing Mermaid class-grammar bug for unresolved
inheritance: the renderer used a flowchart arrow. A regression now verifies the
class-compatible dotted arrow. Unresolved class relationships remain explicitly
labelled, and static call ordering is not presented as a runtime trace.

Verification on 2026-09-27:

- Backend: 359 passed, 37 PostgreSQL-dependent skips; existing Starlette warning.
- Frontend: 77 passed; TypeScript and production build passed, with the existing
  Mermaid bundle-size warning.
- Three endpoint regressions initially failed before implementation. They cover
  both formats, standalone classes, session protection, pinned historical reports,
  foreign/missing analysis IDs and graph limits.
- Client contract tests reject stale identities and incomplete bundles.
- Restarted the local application with the installed AI worker. Browser checks
  used the saved real PyPA sampleproject analysis and rendered all three Mermaid
  views. Downloaded `.mmd` and `.puml` files contained the selected source.
- English/Turkish controls, keyboard selection and 2560x1440 / 390x844 layouts
  were checked using local Edge via Playwright (dedicated Browser skill absent).
  No page errors or horizontal page overflow. Source-toggle checkbox sizing was
  corrected after screenshot inspection.

The model was not called to generate diagrams; this feature uses static parser
evidence. Earlier analysis graphs are preserved, including their historical
limitations; reanalysis is needed to update those graphs.
