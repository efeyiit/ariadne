# Diagram renderers (T18)

`render_diagrams(graph, structures=None)` accepts the inert `DependencyGraph` produced by T10 and returns class, sequence, and component views in Mermaid and PlantUML source. Pass the original parser `FileStructure` values as `structures` so class views can distinguish parsed classes from functions and methods; without them, only inheritance endpoints have enough class evidence to appear. The same output can be obtained one view at a time with `render_mermaid(graph, view, structures=None)` and `render_plantuml(graph, view, structures=None)`, where `view` is `class`, `sequence`, or `component`.

Class views include parsed classes and resolved inheritance. Component views show
file-level dependencies with arrows from the dependent file to its dependency.
Symbol-level calls and inheritance are projected onto their containing files;
same-file relationships are omitted and repeated identical relationships are
collapsed. Resolved edges are solid and carry their kind/status. Unresolved or
external relationships use dashed edges to explicitly labelled placeholder nodes,
including candidates or the missing-evidence reason. They never select the first
candidate or draw a fake self-dependency. Detailed source locations remain in
the underlying dependency graph.

Sequence views include call edges only. Because T10 parser call locations are
static syntax evidence, sequence messages and the diagram note label the ordering
as inferred, never as a runtime trace. Unresolved calls appear as self messages
with their unresolved status and no invented target.

Inputs are validated, limited to 500 nodes and 2,000 edges, and deterministically sorted. Component views can add at most one placeholder per input edge. IDs are SHA-256-derived from graph node IDs or unresolved relationship identities; labels are bounded and escaped. Renderers emit a fixed grammar and do not interpret repository text as Mermaid syntax, HTML, PlantUML directives, or URLs. Empty graphs are supported.

Run focused fixtures built with the actual Python and TypeScript parsers:

```text
cd backend
uv run --no-sync pytest -q tests/diagrams
```

Renderer syntax was checked locally against Mermaid CLI 11.17.0 / Mermaid 11.17.2 and PlantUML 1.2026.8 using synthetic Python and TypeScript parser fixtures. Each of the three views in both formats rendered to SVG or PNG; no repository source content was sent to a remote renderer. Focused automated tests also cover structural output and injection boundaries.
