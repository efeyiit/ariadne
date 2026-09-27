"""Build a conservative dependency graph from the five inert parser outputs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import PurePosixPath
import re
from typing import Literal

from app.contracts.analysis import SourceLocation, WireModel


Language = Literal["python", "typescript", "java", "csharp", "cpp"]
Status = Literal["resolved", "external", "ambiguous"]
Kind = Literal["import", "call", "inheritance"]


class DependencyNode(WireModel):
    id: str
    kind: Literal["file", "symbol"]
    language: Language
    name: str
    location: SourceLocation


class DependencyEdge(WireModel):
    source: str
    target: str | None
    kind: Kind
    status: Status
    expression: str
    location: SourceLocation
    candidates: list[str]
    reason: str | None


class DependencyGraph(WireModel):
    nodes: list[DependencyNode]
    edges: list[DependencyEdge]
    cycles: list[list[str]]
    critical_nodes: list[str]


_EXTENSIONS: dict[Language, tuple[str, ...]] = {
    "python": (".py",),
    "typescript": (".ts", ".tsx", ".mts", ".cts"),
    "java": (".java",),
    "csharp": (".cs",),
    "cpp": (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h"),
}
_IDENTIFIER = re.compile(r"^[A-Za-z_$][\w$]*(?:(?:\.|::)[A-Za-z_$][\w$]*)*$")


def _language(path: str) -> Language:
    for language, extensions in _EXTENSIONS.items():
        if path.endswith(extensions):
            return language
    raise ValueError(f"unsupported source path: {path}")


def _safe_join(base: str, relative: str) -> str | None:
    """Normalize syntax-only paths without allowing a repository-root escape."""
    if relative.startswith("/") or "\\" in relative or re.match(r"^[A-Za-z]:", relative):
        return None
    parts = [part for part in base.split("/") if part]
    for part in relative.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def _symbol_id(path: str, qualified: str) -> str:
    return f"symbol:{path}:{qualified}"


def _file_id(path: str) -> str:
    return f"file:{path}"


def _cycles(adjacency: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan SCCs; report only actual cyclic components."""
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    active: set[str] = set()
    result: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        active.add(node)
        for target in sorted(adjacency[node]):
            if target not in indices:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in active:
                low[node] = min(low[node], indices[target])
        if low[node] == indices[node]:
            component = []
            while True:
                member = stack.pop()
                active.remove(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1 or node in adjacency[node]:
                result.append(sorted(component))

    for node in sorted(adjacency):
        if node not in indices:
            visit(node)
    return sorted(result)


def analyze_dependencies(structures: Iterable[object]) -> DependencyGraph:
    """Analyze parser FileStructure values only; never read or execute repository files.

    A missing local reference is ambiguous; an unqualified external module is
    external. The parser's source location is retained on every relationship.
    """
    files = list(structures)
    by_path: dict[str, object] = {}
    languages: dict[str, Language] = {}
    for file in files:
        path = file.path
        SourceLocation(path=path, start_line=1, end_line=1)
        if path in by_path:
            raise ValueError(f"duplicate source path: {path}")
        by_path[path] = file
        languages[path] = _language(path)
        for group in (file.symbols, file.imports, file.calls, file.inheritance):
            if any(item.location.path != path for item in group):
                raise ValueError(f"foreign source location in {path}")
    files = sorted(files, key=lambda file: file.path)
    nodes: list[DependencyNode] = []
    symbols: dict[str, dict[str, str]] = defaultdict(dict)
    symbol_kinds: dict[str, str] = {}
    qualified: dict[Language, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for file in files:
        path = file.path
        language = languages[path]
        nodes.append(DependencyNode(id=_file_id(path), kind="file", language=language,
                                    name=path, location=SourceLocation(path=path, start_line=1, end_line=1)))
        for symbol in file.symbols:
            if symbol.kind in ("variable", "namespace"):
                continue
            identity = _symbol_id(path, symbol.qualified_name)
            if symbol.qualified_name in symbols[path]:
                # Parser signatures do not distinguish overloads; never invent one.
                symbols[path][symbol.qualified_name] = ""
                continue
            symbols[path][symbol.qualified_name] = identity
            symbol_kinds[identity] = symbol.kind
            qualified[language][symbol.qualified_name].add(identity)
            nodes.append(DependencyNode(id=identity, kind="symbol", language=language,
                                        name=symbol.qualified_name, location=symbol.location))
    nodes = [node for node in nodes if node.kind == "file" or symbols[node.location.path].get(node.name) == node.id]
    node_paths = {node.id: node.location.path for node in nodes}

    python_modules: dict[str, set[str]] = defaultdict(set)
    python_absolute_modules: dict[str, set[str]] = defaultdict(set)
    for path in by_path:
        if languages[path] == "python":
            module = path[:-3].replace("/", ".")
            if module.endswith(".__init__"):
                module = module[:-9]
            python_modules[module].add(path)
            python_absolute_modules[module].add(path)
            # Conventional repository-root src layout. Keep original paths for
            # relative imports; aliases must not change their package anchor.
            # Runtime sys.path order is unknown, so retain competing candidates.
            if path.startswith("src/") and module.startswith("src."):
                python_absolute_modules[module[4:]].add(path)

    def paths_for_module(path: str, name: str) -> tuple[set[str], str | None, str | None]:
        language = languages[path]
        if language == "python":
            modules = python_modules if name.startswith(".") else python_absolute_modules
            if name.startswith("."):
                level = len(name) - len(name.lstrip("."))
                module_parts = path[:-3].split("/")[:-1]
                if level > len(module_parts) + 1:
                    return set(), None, "path_outside_repository"
                module_parts = module_parts[:len(module_parts) - level + 1]
                full = ".".join([*module_parts, name[level:]]).strip(".")
                if not full:
                    return set(), None, "missing_local_target"
            else:
                full = name
            for prefix in (".".join(full.split(".")[:end]) for end in range(len(full.split(".")), 0, -1)):
                if modules[prefix]:
                    member = full[len(prefix):].lstrip(".") or None
                    if member and not any(
                        qname == member for candidate in modules[prefix]
                        for qname in symbols[candidate]
                    ):
                        return set(), None, "missing_local_member"
                    return modules[prefix], member, None
            return set(), None, "missing_local_target" if name.startswith(".") else "external"
        if language == "typescript":
            if not name.startswith("."):
                return set(), None, "external"
            parent = str(PurePosixPath(path).parent)
            base = "" if parent == "." else parent
            # Parser encodes named imports as './module.exportName'.
            for candidate_name, member in [(name, None), (name.rpartition(".")[0], name.rpartition(".")[2])]:
                normalized = _safe_join(base, candidate_name)
                if normalized is None:
                    return set(), None, "path_outside_repository"
                candidates = {candidate for candidate in (
                    normalized, *(normalized + ext for ext in _EXTENSIONS["typescript"]),
                    *(normalized + "/index" + ext for ext in _EXTENSIONS["typescript"]),
                ) if candidate in by_path and languages[candidate] == language}
                if candidates:
                    return candidates, member, None
            return set(), None, "missing_local_target"
        if language == "cpp":
            parent = str(PurePosixPath(path).parent)
            normalized = _safe_join("" if parent == "." else parent, name)
            if normalized is None:
                return set(), None, "path_outside_repository"
            candidates = {candidate for candidate in (normalized, _safe_join("", name))
                          if candidate in by_path and languages[candidate] == language}
            return candidates, None, None if candidates else "missing_include"
        if language == "java":
            prefix = name.removesuffix(".*")
            matches = {node_paths[identity] for qname, identities in qualified[language].items()
                       if qname == prefix or (name.endswith(".*") and qname.startswith(prefix + "."))
                       for identity in identities if identity in node_paths}
            known_package = any(getattr(file, "package", None) == prefix.rpartition(".")[0]
                                for file in files)
            return matches, None, None if matches else "missing_local_target" if known_package else "external"
        # C# using can name a type or namespace, and namespaces span files.
        matches = {node_paths[identity] for qname, identities in qualified[language].items()
                   if qname == name or qname.startswith(name + ".")
                   for identity in identities if identity in node_paths}
        known_namespace = any(symbol.kind == "namespace" and
                              (symbol.qualified_name == name.rpartition(".")[0] or
                               symbol.qualified_name.startswith(name.rpartition(".")[0] + "."))
                              for file in files for symbol in file.symbols)
        return matches, None, None if matches else "missing_local_target" if known_namespace else "external"

    edges: list[DependencyEdge] = []
    imported_files: dict[str, set[str]] = defaultdict(set)
    bindings: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    def exported_symbol(path: str, name: str, seen: frozenset[tuple[str, str]] = frozenset()) -> set[str]:
        key = (path, name)
        if key in seen:
            return set()
        found: set[str] = set()
        for export in getattr(by_path[path], "exports", []):
            public_name = export.alias or export.name
            if export.name == "*" and export.alias:
                continue  # namespace export does not expose its members as local names
            if public_name != name and export.name != "*":
                continue
            if export.source:
                targets, _, _ = paths_for_module(path, export.source)
                for target in targets:
                    found.update(exported_symbol(target, export.name if export.name != "*" else name,
                                                 seen | {key}))
            elif export.name != "*":
                found.update(identity for qname, identity in symbols[path].items()
                             if identity and qname.rsplit(".", 1)[-1] == export.name)
        return found

    def add(source: str, candidates: set[str], kind: Kind, expression: str,
            location: SourceLocation, missing: str | None = None) -> None:
        valid = sorted(candidate for candidate in candidates if candidate in node_paths)
        status: Status = "resolved" if len(valid) == 1 else "ambiguous" if valid or missing != "external" else "external"
        edges.append(DependencyEdge(source=source, target=valid[0] if status == "resolved" else None,
                                    kind=kind, status=status, expression=expression,
                                    location=location, candidates=valid,
                                    reason=None if status == "resolved" else missing or "multiple_targets"))

    for file in files:
        path = file.path
        reexports_seen: set[tuple[str, int]] = set()
        for item in file.imports:
            dynamic = languages[path] == "cpp" and any(
                uncertainty.reason == "dynamic_include" and uncertainty.location == item.location
                for uncertainty in getattr(file, "macro_uncertainties", []))
            targets, member, reason = (set(), None, "dynamic_include") if dynamic else paths_for_module(path, item.name)
            imported_files[path].update(targets)
            add(_file_id(path), {_file_id(p) for p in targets}, "import", item.name, item.location, reason)
            if len(targets) == 1 and member:
                target_path = next(iter(targets))
                if languages[path] == "typescript":
                    matches = exported_symbol(target_path, member)
                else:
                    matches = {identity for qname, identity in symbols[target_path].items()
                               if identity and qname.rsplit(".", 1)[-1] == member}
                bindings[path][item.alias or member].update(matches)
            if len(targets) == 1 and item.alias and not member and languages[path] == "python":
                target_path = next(iter(targets))
                bindings[path][item.alias].add(_file_id(target_path))
            if languages[path] in ("java", "csharp"):
                matches = qualified[languages[path]].get(item.name, set())
                if matches:
                    bindings[path][item.alias or item.name.rsplit(".", 1)[-1]].update(matches)
        if languages[path] == "typescript":
            for export in file.exports:
                if export.source:
                    marker = (export.source, export.location.start_line)
                    if marker in reexports_seen:
                        continue
                    reexports_seen.add(marker)
                    targets, _, reason = paths_for_module(path, export.source)
                    imported_files[path].update(targets)
                    add(_file_id(path), {_file_id(p) for p in targets}, "import",
                        export.source, export.location, reason)

    def local_symbols(path: str, expression: str, scope: str | None) -> set[str]:
        language = languages[path]
        separator = "::" if language == "cpp" else "."
        names = [expression]
        if scope:
            parts = scope.split(separator)
            names = [separator.join([*parts[:end], expression]) for end in range(len(parts), 0, -1)] + names
        return {symbols[path][name] for name in names if symbols[path].get(name)}

    for file in files:
        path = file.path
        language = languages[path]
        for item in file.calls:
            expression = item.callee
            source = symbols[path].get(item.scope or "") or _file_id(path)
            candidates: set[str] = set()
            if _IDENTIFIER.fullmatch(expression):
                if expression.startswith(("self.", "this.")) and item.scope:
                    owner = item.scope.rpartition(".")[0]
                    candidates |= local_symbols(path, owner + "." + expression.split(".", 1)[1], None)
                elif "." not in expression and "::" not in expression:
                    candidates |= local_symbols(path, expression, item.scope)
                    candidates |= bindings[path].get(expression, set())
                    if language == "cpp":
                        for imported in imported_files[path]:
                            candidates |= local_symbols(imported, expression, None)
                else:
                    candidates |= local_symbols(path, expression, None)
                    if language in ("java", "csharp") and expression.count(".") >= 1:
                        candidates |= qualified[language].get(expression, set())
                    first, _, remainder = expression.partition(".")
                    for bound in bindings[path].get(first, set()):
                        if bound.startswith("file:"):
                            candidates |= local_symbols(bound[5:], remainder, None)
                        elif bound.startswith("symbol:") and remainder:
                            bound_path = node_paths.get(bound)
                            bound_name = bound.rpartition(":")[2]
                            if bound_path:
                                candidates |= local_symbols(bound_path, bound_name + "." + remainder, None)
            candidates.discard("")
            # A file binding is not a callable target.
            candidates = {candidate for candidate in candidates
                          if symbol_kinds.get(candidate) in ("class", "struct", "function", "method")}
            add(source, candidates, "call", expression, item.location, "dynamic_or_unbound_call")
        for item in file.inheritance:
            source = symbols[path].get(item.class_name) or _file_id(path)
            base = item.base_name
            candidates: set[str] = set()
            if _IDENTIFIER.fullmatch(base):
                candidates |= local_symbols(path, base, item.class_name.rpartition(".")[0] or None)
                candidates |= bindings[path].get(base, set())
                if language in ("java", "csharp") and "." in base:
                    candidates |= qualified[language].get(base, set())
                if language in ("java", "csharp") and "." not in base:
                    prefix = item.class_name.rpartition(".")[0]
                    candidates |= qualified[language].get(prefix + "." + base, set())
                if language == "cpp":
                    for imported in imported_files[path]:
                        candidates |= local_symbols(imported, base, None)
            candidates = {candidate for candidate in candidates
                          if symbol_kinds.get(candidate) in ("class", "interface", "struct")}
            add(source, candidates, "inheritance", base, item.location, "dynamic_or_unbound_base")

    adjacency: dict[str, set[str]] = {_file_id(path): set() for path in by_path}
    degree: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.status != "resolved" or edge.target is None:
            continue
        source_path = node_paths[edge.source]
        target_path = node_paths[edge.target]
        if source_path != target_path:
            source_file, target_file = _file_id(source_path), _file_id(target_path)
            adjacency[source_file].add(target_file)
            degree[source_file].add(target_file)
            degree[target_file].add(source_file)
    critical = sorted((node for node, neighbors in degree.items() if len(neighbors) >= 2),
                      key=lambda node: (-len(degree[node]), node))
    return DependencyGraph(nodes=nodes, edges=edges, cycles=_cycles(adjacency),
                           critical_nodes=critical)
