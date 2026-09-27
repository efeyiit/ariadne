"""Render T10 dependency graphs as Mermaid and PlantUML source.

All repository-derived strings are treated as untrusted labels. Renderers emit
only fixed grammar, generated identifiers, and escaped display text; no input
is interpreted as a directive or URL.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from collections.abc import Iterable
from typing import Literal

from app.analyzers.dependencies.graph import DependencyGraph, DependencyNode, DependencyEdge


View = Literal["class", "sequence", "component"]
Format = Literal["mermaid", "plantuml"]
MAX_NODES = 500
MAX_EDGES = 2_000
MAX_LABEL_LENGTH = 240


@dataclass(frozen=True)
class DiagramBundle:
    class_diagram: str
    sequence_diagram: str
    component_diagram: str


def _graph(value: DependencyGraph | dict) -> DependencyGraph:
    graph = value if isinstance(value, DependencyGraph) else DependencyGraph.model_validate(value)
    if len(graph.nodes) > MAX_NODES or len(graph.edges) > MAX_EDGES:
        raise ValueError(f"diagram graph exceeds limits ({MAX_NODES} nodes, {MAX_EDGES} edges)")
    ids = [n.id for n in graph.nodes]
    if len(set(ids)) != len(ids):
        raise ValueError("diagram graph contains duplicate node IDs")
    known = set(ids)
    if any(e.source not in known or (e.target is not None and e.target not in known) or
           any(c not in known for c in e.candidates) for e in graph.edges):
        raise ValueError("diagram edge references an unknown node")
    return graph


def _nodes(graph: DependencyGraph) -> list[DependencyNode]:
    return sorted(graph.nodes, key=lambda n: (n.kind, n.location.path, n.name, n.id))


def _edges(graph: DependencyGraph) -> list[DependencyEdge]:
    return sorted(graph.edges, key=lambda e: (e.location.path, e.location.start_line,
                                               e.kind, e.expression, e.status,
                                               e.source, e.target or "", tuple(e.candidates)))


def _ids(graph: DependencyGraph) -> dict[str, str]:
    # Hash IDs never contain source text and remain stable across runs.
    return {node.id: "n_" + hashlib.sha256(node.id.encode("utf-8")).hexdigest()[:16]
            for node in _nodes(graph)}


def _class_ids(graph: DependencyGraph, structures: Iterable[object] | None) -> set[str]:
    if structures is not None:
        return {
            f"symbol:{file.path}:{symbol.qualified_name}"
            for file in structures for symbol in file.symbols if symbol.kind == "class"
        }
    # T10's graph schema does not preserve the parser symbol kind. Without
    # parser structures, only inheritance endpoints have direct class evidence.
    return {node_id for edge in graph.edges if edge.kind == "inheritance"
            for node_id in (edge.source, edge.target) if node_id is not None}


def _label(value: str) -> str:
    # JSON escaping is suitable for quoted labels in both target grammars;
    # additionally neutralize markup and line-breaking/control characters.
    value = value[:MAX_LABEL_LENGTH]
    safe = "".join(ch if ch >= " " and ch not in "\u007f\u2028\u2029" else " " for ch in value)
    # Mermaid treats semicolons as a statement terminator in several grammars
    # and colons/arrow spellings as separators. Display neutral Unicode forms.
    safe = safe.replace(";", "；").replace(":", "：")
    safe = safe.replace("->", "→").replace("<-", "←")
    # PlantUML directives begin with !; encode their introducer in displayed
    # text so even a parser edge case cannot reinterpret it as a directive.
    safe = safe.replace("!", "&#33;")
    safe = safe.replace("<", "&lt;").replace(">", "&gt;")
    return json.dumps(safe, ensure_ascii=False)[1:-1]


def _display(node: DependencyNode) -> str:
    return _label(node.name)


def _mermaid_label(value: str) -> str:
    # Mermaid's quoted strings do not use JSON backslash escaping.
    return _label(value).replace('\\"', "＂").replace("\\\\", "＼")


def _relation(edge: DependencyEdge) -> str:
    return f"{edge.kind} {edge.status} {edge.expression}"


def _target_label(edge: DependencyEdge, by_id: dict[str, DependencyNode]) -> str:
    if edge.status == "resolved" and edge.target:
        return by_id[edge.target].name
    if edge.candidates:
        return "candidates: " + ", ".join(by_id[item].name for item in edge.candidates)
    return edge.reason or edge.status


def _component(graph: DependencyGraph, format: Format) -> str:
    """Project symbol relationships onto files without inventing target files."""
    nodes, ids = _nodes(graph), _ids(graph)
    by_id = {node.id: node for node in nodes}
    files = {node.location.path: node for node in nodes if node.kind == "file"}
    mermaid = format == "mermaid"
    label = _mermaid_label if mermaid else _label
    lines = ["flowchart LR"] if mermaid else ["@startuml", "hide empty members"]

    def declare(identity: str, name: str) -> None:
        lines.append(f'{identity}["{label(name)}"]' if mermaid
                     else f'component "{label(name)}" as {identity}')

    for node in files.values():
        declare(ids[node.id], node.name)
    emitted: set[tuple[str, str, str]] = set()
    placeholders: set[str] = set()
    for edge in _edges(graph):
        source_file = files.get(by_id[edge.source].location.path)
        if source_file is None:
            continue
        src = ids[source_file.id]
        resolved = edge.status == "resolved" and edge.target is not None
        if resolved:
            target_file = files.get(by_id[edge.target].location.path)
            if target_file is None or target_file.id == source_file.id:
                continue  # Internal calls are not file-level dependencies.
            dst = ids[target_file.id]
        else:
            # A placeholder describes missing evidence, never a chosen candidate
            # or a self-dependency. Sort candidates for deterministic rendering.
            key = (src, edge.kind, edge.status, edge.expression,
                   tuple(sorted(edge.candidates)), edge.reason)
            dst = "u_" + hashlib.sha256(json.dumps(key).encode("utf-8")).hexdigest()[:16]
            if dst not in placeholders:
                detail = ("candidates: " + ", ".join(by_id[item].name for item in sorted(edge.candidates))
                          if edge.candidates else edge.reason or edge.status)
                declare(dst, f"{edge.status}: {edge.expression} — {detail}")
                placeholders.add(dst)
        relation = _relation(edge)
        key = (src, dst, relation)
        if key in emitted:
            continue
        emitted.add(key)
        if mermaid:
            arrow = "-->" if resolved else "-.->"
            lines.append(f'{src} {arrow}|"{label(relation)}"| {dst}')
        else:
            arrow = "-->" if resolved else "..>"
            lines.append(f'{src} {arrow} {dst} : "{label(relation)}"')
    if not mermaid:
        lines.append("@enduml")
    return "\n".join(lines) + "\n"


def _mermaid(graph: DependencyGraph, view: View, structures: Iterable[object] | None = None) -> str:
    if view == "component":
        return _component(graph, "mermaid")
    nodes, edges, ids = _nodes(graph), _edges(graph), _ids(graph)
    by_id = {node.id: node for node in nodes}
    class_ids = _class_ids(graph, structures)
    lines = ["classDiagram" if view == "class" else "sequenceDiagram" if view == "sequence" else "flowchart LR"]
    if view == "sequence":
        participants: set[str] = set()
        for edge in edges:
            if edge.kind != "call":
                continue
            refs = [edge.source, edge.target] if edge.status == "resolved" and edge.target else [edge.source, *edge.candidates]
            for ref in refs:
                if ref and ref in ids and ref not in participants:
                    lines.append(f"participant {ids[ref]} as \"{_mermaid_label(by_id[ref].name)}\"")
                    participants.add(ref)
        if participants:
            first = ids[sorted(participants)[0]]
            lines.append(f"Note over {first}: Inferred static call order, not a runtime trace")
        else:
            lines.extend(["participant Inferred", "Note over Inferred: Inferred static call order, not a runtime trace",
                          "Inferred->>Inferred: No call edges; inferred sequence unavailable"])
        for edge in edges:
            if edge.kind != "call":
                continue
            src = ids[edge.source]
            if edge.status == "resolved" and edge.target:
                lines.append(f"{src} ->> {ids[edge.target]}: {_mermaid_label(_relation(edge))} (inferred)")
            else:
                lines.append(f"{src} ->> {src}: {_mermaid_label(_relation(edge) + ' target ' + _target_label(edge, by_id))} (inferred, unresolved)")
        return "\n".join(lines) + "\n"

    for node in nodes:
        if view == "class" and (node.kind != "symbol" or node.id not in class_ids):
            continue
        if view == "component" and node.kind != "file":
            continue
        if view == "class":
            lines.append(f'class {ids[node.id]}["{_mermaid_label(node.name)}"]')
        else:
            lines.append(f"{ids[node.id]}[\"{_mermaid_label(node.name)}\"]")

    kinds = {"inheritance"} if view == "class" else {"import", "call", "inheritance"}
    for edge in edges:
        if edge.kind not in kinds:
            continue
        src_node = by_id[edge.source]
        if view == "class" and (src_node.kind != "symbol" or src_node.id not in class_ids or edge.kind != "inheritance"):
            continue
        if view == "component" and src_node.kind != "file":
            continue
        if edge.status == "resolved" and edge.target:
            dst = by_id[edge.target]
            if view == "class" and (dst.kind != "symbol" or dst.id not in class_ids):
                continue
            if view == "component" and dst.kind != "file":
                continue
            arrow = " <|-- " if view == "class" else " --> "
            if view == "component":
                lines.append(f"{ids[edge.target]} -->|{_mermaid_label(_relation(edge))}| {ids[edge.source]}")
            else:
                lines.append(f"{ids[edge.target]}{arrow}{ids[edge.source]} : {_mermaid_label(_relation(edge))}")
        else:
            candidates = edge.candidates or []
            suffix = _target_label(edge, by_id)
            target_id = ids[candidates[0]] if candidates else ids[edge.source]
            if view == "component":
                lines.append(f"{ids[edge.source]} -.->|{_mermaid_label(_relation(edge) + ' -> ' + suffix)}| {target_id}")
            else:
                lines.append(f"{ids[edge.source]} -.-> {target_id} : {_mermaid_label(_relation(edge) + ' -> ' + suffix)}")
    return "\n".join(lines) + "\n"


def _plantuml(graph: DependencyGraph, view: View, structures: Iterable[object] | None = None) -> str:
    if view == "component":
        return _component(graph, "plantuml")
    nodes, edges, ids = _nodes(graph), _edges(graph), _ids(graph)
    by_id = {node.id: node for node in nodes}
    class_ids = _class_ids(graph, structures)
    keyword = "class" if view == "class" else "participant" if view == "sequence" else "component"
    lines = ["@startuml", "hide empty members"]
    if view == "sequence":
        if nodes:
            lines.extend([f"note over {ids[nodes[0].id]}", "Inferred static call order, not a runtime trace", "end note"])
        else:
            lines.extend(["note", "Inferred static call order, not a runtime trace", "end note"])
        emitted: set[str] = set()
        for edge in edges:
            if edge.kind != "call":
                continue
            refs = [edge.source, edge.target] if edge.status == "resolved" and edge.target else [edge.source, *edge.candidates]
            for ref in refs:
                if ref and ref in ids and ref not in emitted:
                    lines.append(f'{keyword} "{_display(by_id[ref])}" as {ids[ref]}')
                    emitted.add(ref)
        for edge in edges:
            if edge.kind != "call":
                continue
            src = ids[edge.source]
            if edge.status == "resolved" and edge.target:
                lines.append(f'{src} -> {ids[edge.target]} : {_label(_relation(edge) + " (inferred)")}')
            else:
                lines.extend([f"note over {src}", _label(_relation(edge) + " -> " + _target_label(edge, by_id)), "end note"])
        lines.append("@enduml")
        return "\n".join(lines) + "\n"

    for node in nodes:
        if view == "class" and (node.kind != "symbol" or node.id not in class_ids):
            continue
        if view == "component" and node.kind != "file":
            continue
        lines.append(f'{keyword} "{_display(node)}" as {ids[node.id]}')
    kinds = {"inheritance"} if view == "class" else {"import", "call", "inheritance"}
    for edge in edges:
        if edge.kind not in kinds:
            continue
        src_node = by_id[edge.source]
        if view == "class" and (src_node.kind != "symbol" or src_node.id not in class_ids or edge.kind != "inheritance"):
            continue
        if view == "component" and src_node.kind != "file":
            continue
        if edge.status == "resolved" and edge.target:
            dst = by_id[edge.target]
            if view == "class" and (dst.kind != "symbol" or dst.id not in class_ids):
                continue
            if view == "component" and dst.kind != "file":
                continue
            arrow = " <|-- " if view == "class" else " --> "
            lines.append(f'{ids[edge.target]}{arrow}{ids[edge.source]} : "{_label(_relation(edge))}"')
        else:
            candidates = edge.candidates or []
            dst = ids[candidates[0]] if candidates else ids[edge.source]
            lines.append(f'{ids[edge.source]} ..> {dst} : "{_label(_relation(edge) + " -> " + _target_label(edge, by_id))}"')
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def render_mermaid(graph: DependencyGraph | dict, view: View,
                   structures: Iterable[object] | None = None) -> str:
    """Render one view to Mermaid source, without parsing or executing labels."""
    if view not in ("class", "sequence", "component"):
        raise ValueError("view must be class, sequence, or component")
    return _mermaid(_graph(graph), view, structures)


def render_plantuml(graph: DependencyGraph | dict, view: View,
                    structures: Iterable[object] | None = None) -> str:
    """Render one view to PlantUML source; repository directives stay inert labels."""
    if view not in ("class", "sequence", "component"):
        raise ValueError("view must be class, sequence, or component")
    return _plantuml(_graph(graph), view, structures)


def render_diagrams(graph: DependencyGraph | dict,
                    structures: Iterable[object] | None = None) -> dict[Format, DiagramBundle]:
    """Render class, inferred sequence, and component views in both formats."""
    validated = _graph(graph)
    parser_structures = tuple(structures) if structures is not None else None
    return {
        "mermaid": DiagramBundle(*(_mermaid(validated, view, parser_structures) for view in ("class", "sequence", "component"))),
        "plantuml": DiagramBundle(*(_plantuml(validated, view, parser_structures) for view in ("class", "sequence", "component"))),
    }
