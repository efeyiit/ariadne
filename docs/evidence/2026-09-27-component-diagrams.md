# File dependency diagrams and live analysis

Component diagrams previously reversed dependency arrows, omitted symbol-level
calls and inheritance, and sent unresolved edges to the first candidate or back
to the source file. Both Mermaid and PlantUML now share a file projection:

- Arrows go from the dependent file to its dependency.
- Cross-file symbol calls and inheritance appear between their containing files.
- Same-file relationships are omitted; identical repeated relationships collapse.
- External and ambiguous targets have explicit placeholder nodes. No candidate
  is chosen without resolution evidence.

The sandbox preview also preserves the generated SVG's intrinsic size. Large
graphs scroll inside the iframe instead of shrinking text to fit its height.
SVG validation, script-free sandboxing and restrictive CSP remain in place.

Verified on 2026-09-27:

- Six backend regression cases failed before the fix; 13 diagram tests passed.
- Full backend suite: 355 passed, 37 PostgreSQL-dependent skips, existing
  Starlette deprecation warning.
- Frontend suite: 75 passed; TypeScript check and production build passed.
  The existing large Mermaid chunk warning remains.
- Restarted the local application with the installed model. Regenerated the
  stored public PyPA sampleproject snapshot at commit
  `621e4974ca25ce531773def586ba3ed8e736b3fc`.
- The real report resolved `sample.simple.add_one` to `src/sample/simple.py`,
  including the callable edge. AI was available and the project-purpose answer
  completed. This is a smoke check, not general model accuracy certification.
- The generated Mermaid SVG rendered in the sandbox with no page errors.
  Playwright with local Edge checked 2560x1440 and 390x844 viewports; the dedicated
  Browser skill was unavailable. The page had no horizontal overflow, while the
  iframe supported internal scrolling. SVG width matched its 754.609375-unit
  viewBox at native scale instead of being compressed into the frame.

PlantUML output was regression-tested as source; its rendered image was not
revalidated in this run. Class and sequence view semantics are unchanged. Static
relationships do not establish runtime execution order, and unresolved external
calls are still explicitly uncertain. Earlier saved reports remain historical;
reanalysis produces the corrected graph.
