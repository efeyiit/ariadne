"""Diagram fixtures built from the real Python and TypeScript parser outputs."""

import pytest
import re

from app.analyzers.dependencies import analyze_dependencies
from app.analyzers.dependencies.graph import DependencyGraph, DependencyNode
from app.diagrams import render_diagrams, render_mermaid, render_plantuml
from app.parsers import python, typescript


def parsed(parser, path, source):
    result = parser.parse_file(path, source)
    assert not result.errors, result.errors
    return result


def structures():
    return [
        parsed(python, "pkg/base.py", "class Base:\n    def work(self): pass\n"),
        parsed(python, "pkg/app.py", "from .base import Base\nclass App(Base):\n    def run(self):\n        self.work()\n        print('ok')\n"),
        parsed(typescript, "web/client.ts", "import { send } from './service';\nexport class Client { run() { send(); } }\n"),
        parsed(typescript, "web/service.ts", "export function send() {}\n"),
    ]


def graph():
    return analyze_dependencies(structures())


def test_all_views_in_both_formats_from_real_parser_graph():
    result = render_diagrams(graph(), structures())
    assert set(result) == {"mermaid", "plantuml"}
    for bundle in result.values():
        assert "classDiagram" in bundle.class_diagram or "@startuml" in bundle.class_diagram
        assert "inferred" in bundle.sequence_diagram.lower()
        assert "runtime trace" in bundle.sequence_diagram.lower()
        assert "flowchart LR" in bundle.component_diagram or "@startuml" in bundle.component_diagram
        assert "external" in bundle.component_diagram or "ambiguous" in bundle.component_diagram or "resolved" in bundle.component_diagram


def test_static_calls_are_marked_inferred_and_external_call_is_not_resolved():
    result = graph()
    sequence = render_mermaid(result, "sequence")
    assert "Inferred static call order, not a runtime trace" in sequence
    assert "(inferred)" in sequence
    assert "call ambiguous print" in sequence


def test_untrusted_labels_cannot_create_diagram_directives_or_markup():
    node = DependencyNode(id="file:evil.py", kind="file", language="python",
                          name='Injected"\n!include https://bad.example<img>',
                          location={"path": "evil.py", "start_line": 1, "end_line": 1})
    source = DependencyGraph(nodes=[node], edges=[], cycles=[], critical_nodes=[])
    rendered = render_plantuml(source, "component")
    mermaid = render_mermaid(source, "component")
    assert "!include https://bad.example" not in rendered
    assert "<img>" not in rendered
    assert "&lt;img&gt;" in rendered
    assert rendered.count("@startuml") == rendered.count("@enduml") == 1
    assert "!include https://bad.example" not in mermaid
    assert "<img>" not in mermaid
    assert "&lt;img&gt;" in mermaid
    assert "＂" in mermaid
    # IDs are generated from hashes, never copied from repository labels.
    assert " as n_" in rendered


def test_deterministic_order_unicode_and_special_characters():
    first = graph()
    second = DependencyGraph(nodes=list(reversed(first.nodes)), edges=list(reversed(first.edges)),
                             cycles=list(reversed(first.cycles)), critical_nodes=list(reversed(first.critical_nodes)))
    assert render_diagrams(first) == render_diagrams(second)
    assert "pkg/app.py" in render_mermaid(first, "component")
    unicode_node = DependencyNode(id="file:unicode.py", kind="file", language="python",
                                  name="Sınıf λ", location={"path": "unicode.py", "start_line": 1, "end_line": 1})
    unicode_graph = DependencyGraph(nodes=[unicode_node], edges=[], cycles=[], critical_nodes=[])
    assert "Sınıf λ" in render_mermaid(unicode_graph, "component")


def test_parser_symbol_kinds_limit_class_view_to_actual_classes():
    source_structures = [parsed(python, "kinds.py", "class RealClass:\n    pass\ndef helper():\n    pass\n")]
    parsed_graph = analyze_dependencies(source_structures)
    diagram = render_mermaid(parsed_graph, "class", source_structures)
    assert "RealClass" in diagram
    assert "helper" not in diagram


def test_empty_graph_is_valid_and_explicitly_inferred():
    empty = DependencyGraph(nodes=[], edges=[], cycles=[], critical_nodes=[])
    result = render_diagrams(empty)
    assert result["mermaid"].component_diagram == "flowchart LR\n"
    assert "not a runtime trace" in result["mermaid"].sequence_diagram
    assert "@enduml" in result["plantuml"].class_diagram


def test_graph_size_and_reference_limits_are_enforced():
    oversized = DependencyGraph(nodes=[
        {"id": str(i), "kind": "file", "language": "python", "name": str(i),
         "location": {"path": f"{i}.py", "start_line": 1, "end_line": 1}}
        for i in range(501)
    ], edges=[], cycles=[], critical_nodes=[])
    with pytest.raises(ValueError, match="exceeds limits"):
        render_mermaid(oversized, "component")
    malformed = {"nodes": [], "edges": [{"source": "missing", "target": None, "kind": "call",
                  "status": "external", "expression": "x", "location": {"path": "x.py", "start_line": 1, "end_line": 1},
                  "candidates": [], "reason": "external"}], "cycles": [], "critical_nodes": []}
    with pytest.raises(ValueError, match="unknown node"):
        render_plantuml(malformed, "sequence")


def component_id(text, label):
    for line in text.splitlines():
        if f'"{label}"' in line:
            return re.search(r'n_[0-9a-f]+', line).group()
    raise AssertionError(f"Missing component {label}")


@pytest.mark.parametrize("renderer", [render_mermaid, render_plantuml])
def test_component_edges_follow_dependency_direction_and_include_symbol_relations(renderer):
    source = analyze_dependencies([
        parsed(python, "src/lib.py", "class Base: pass\ndef work(): pass\n"),
        parsed(python, "main.py", "from lib import Base, work\nclass Child(Base):\n    def run(self):\n        work()\n"),
    ])
    text = renderer(source, "component")
    main, lib = component_id(text, "main.py"), component_id(text, "src/lib.py")
    for kind in ("import", "call", "inheritance"):
        lines = [line for line in text.splitlines() if f"{kind} resolved" in line]
        assert lines, (kind, text)
        assert all(line.startswith(main + " -->") and lib in line for line in lines), text


@pytest.mark.parametrize("renderer", [render_mermaid, render_plantuml])
def test_unresolved_components_are_explicit_placeholders_not_self_or_first_candidate(renderer):
    source = analyze_dependencies([
        parsed(python, "main.py", "import json\nfrom pkg.util import work\nwork()\n"),
        parsed(python, "pkg/util.py", "def work(): pass\n"),
        parsed(python, "src/pkg/util.py", "def work(): pass\n"),
    ])
    text = renderer(source, "component")
    main = component_id(text, "main.py")
    uncertain = [line for line in text.splitlines() if line.startswith(main) and ("-.->" in line or "..>" in line)]
    assert len(uncertain) == 3, text
    assert all(re.search(r'\bu_[0-9a-f]+\b', line) for line in uncertain), text
    assert "external" in text and "ambiguous" in text
    assert "pkg/util.py" in text and "src/pkg/util.py" in text


@pytest.mark.parametrize("renderer", [render_mermaid, render_plantuml])
def test_component_view_omits_same_file_calls_and_deduplicates_repeated_calls(renderer):
    source = analyze_dependencies([
        parsed(python, "lib.py", "def work(): pass\n"),
        parsed(python, "main.py", "from lib import work\ndef run():\n    work()\n    work()\nrun()\n"),
    ])
    text = renderer(source, "component")
    assert text.count("call resolved work") == 1
    assert "call resolved run" not in text
