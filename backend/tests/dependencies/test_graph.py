"""End-to-end dependency fixtures using the actual language parsers."""

import pytest

from app.analyzers.dependencies import analyze_dependencies
from app.parsers import cpp, csharp, java, python, typescript


def parse(parser, path, source):
    result = parser.parse_file(path, source)
    assert not result.errors, result.errors
    return result


def edge(graph, kind, expression, path):
    matches = [item for item in graph.edges if item.kind == kind and
               item.expression == expression and item.location.path == path]
    assert len(matches) == 1, matches
    return matches[0]


def test_python_relative_import_calls_inheritance_and_cycle():
    graph = analyze_dependencies([
        parse(python, "pkg/a.py", "from .b import Base, work\nclass Child(Base):\n    def run(self):\n        work()\n"),
        parse(python, "pkg/b.py", "from .a import Child\nclass Base: pass\ndef work(): pass\n"),
    ])
    assert edge(graph, "import", ".b.Base", "pkg/a.py").target == "file:pkg/b.py"
    assert edge(graph, "inheritance", "Base", "pkg/a.py").target == "symbol:pkg/b.py:Base"
    assert edge(graph, "call", "work", "pkg/a.py").target == "symbol:pkg/b.py:work"
    assert graph.cycles == [["file:pkg/a.py", "file:pkg/b.py"]]


def test_typescript_named_import_and_reexport_provenance():
    graph = analyze_dependencies([
        parse(typescript, "src/base.ts", "export class Base {}\nexport function work() {}\n"),
        parse(typescript, "src/barrel.ts", "export { Base, work } from './base';\n"),
        parse(typescript, "src/child.ts", "import { Base, work } from './barrel';\nexport class Child extends Base { run() { work(); } }\n"),
    ])
    assert edge(graph, "import", "./barrel.Base", "src/child.ts").target == "file:src/barrel.ts"
    assert edge(graph, "import", "./base", "src/barrel.ts").target == "file:src/base.ts"
    assert edge(graph, "inheritance", "Base", "src/child.ts").target == "symbol:src/base.ts:Base"
    assert edge(graph, "call", "work", "src/child.ts").target == "symbol:src/base.ts:work"


def test_java_package_import_and_ambiguous_same_named_type():
    graph = analyze_dependencies([
        parse(java, "src/lib/Base.java", "package lib; public class Base { public void go() {} }"),
        parse(java, "src/other/Base.java", "package other; public class Base {}"),
        parse(java, "src/app/Child.java", "package app; import lib.Base; public class Child extends Base { void run() { go(); } }"),
    ])
    assert edge(graph, "import", "lib.Base", "src/app/Child.java").target == "file:src/lib/Base.java"
    assert edge(graph, "inheritance", "Base", "src/app/Child.java").target == "symbol:src/lib/Base.java:lib.Base"
    assert edge(graph, "call", "go", "src/app/Child.java").status == "ambiguous"


def test_java_imported_type_qualified_call():
    graph = analyze_dependencies([
        parse(java, "lib/Util.java", "package lib; public class Util { public static void go() {} }"),
        parse(java, "app/Main.java", "package app; import lib.Util; public class Main { void run() { Util.go(); } }"),
    ])
    assert edge(graph, "call", "Util.go", "app/Main.java").target == "symbol:lib/Util.java:lib.Util.go"


def test_csharp_namespace_and_type_alias():
    graph = analyze_dependencies([
        parse(csharp, "Lib/Base.cs", "namespace Lib; public class Base { public void Go() {} }"),
        parse(csharp, "App/Child.cs", "using Alias = Lib.Base; namespace App; public class Child : Alias { void Run() { Go(); } }"),
    ])
    assert edge(graph, "import", "Lib.Base", "App/Child.cs").target == "file:Lib/Base.cs"
    assert edge(graph, "inheritance", "Alias", "App/Child.cs").target == "symbol:Lib/Base.cs:Lib.Base"


def test_csharp_type_alias_qualified_call():
    graph = analyze_dependencies([
        parse(csharp, "Lib/Util.cs", "namespace Lib; public class Util { public static void Go() {} }"),
        parse(csharp, "App/Main.cs", "using Alias = Lib.Util; namespace App; public class Main { void Run() { Alias.Go(); } }"),
    ])
    assert edge(graph, "call", "Alias.Go", "App/Main.cs").target == "symbol:Lib/Util.cs:Lib.Util.Go"


def test_cpp_include_and_repo_boundary():
    graph = analyze_dependencies([
        parse(cpp, "src/base.hpp", "class Base {};\nvoid work();\n"),
        parse(cpp, "src/child.cpp", '#include "base.hpp"\nclass Child : public Base {};\nvoid run() { work(); }\n'),
        parse(cpp, "src/escape.cpp", '#include "../../outside.hpp"\nvoid f() {}\n'),
    ])
    assert edge(graph, "import", "base.hpp", "src/child.cpp").target == "file:src/base.hpp"
    assert edge(graph, "inheritance", "Base", "src/child.cpp").target == "symbol:src/base.hpp:Base"
    assert edge(graph, "call", "work", "src/child.cpp").target == "symbol:src/base.hpp:work"
    bad = edge(graph, "import", "../../outside.hpp", "src/escape.cpp")
    assert (bad.status, bad.reason, bad.target) == ("ambiguous", "path_outside_repository", None)


def test_missing_relative_dynamic_and_duplicate_targets_stay_ambiguous():
    graph = analyze_dependencies([
        parse(python, "a.py", "from .missing import x\ndef f():\n    factory()()\n"),
        parse(python, "one.py", "def same(): pass\n"),
        parse(python, "two.py", "def same(): pass\n"),
    ])
    assert edge(graph, "import", ".missing.x", "a.py").status == "ambiguous"
    assert edge(graph, "call", "factory()", "a.py").status == "ambiguous"


def test_reject_duplicate_paths_and_foreign_locations():
    parsed = parse(python, "a.py", "def f(): pass")
    with pytest.raises(ValueError, match="duplicate"):
        analyze_dependencies([parsed, parsed])
    parsed.symbols[0].location.path = "b.py"
    with pytest.raises(ValueError, match="foreign"):
        analyze_dependencies([parsed])


def test_critical_file_has_two_distinct_neighbors():
    graph = analyze_dependencies([
        parse(python, "hub.py", "import left\nimport right\n"),
        parse(python, "left.py", "def left(): pass\n"),
        parse(python, "right.py", "def right(): pass\n"),
    ])
    assert graph.critical_nodes == ["file:hub.py"]
    assert graph.cycles == []


def test_typescript_escaping_path_and_unexported_name_are_uncertain():
    graph = analyze_dependencies([
        parse(typescript, "src/main.ts", "import { hidden } from '../../escape';\nimport { secret } from './local';\nhidden(); secret();\n"),
        parse(typescript, "src/local.ts", "function secret() {}\n"),
    ])
    escaping = edge(graph, "import", "../../escape.hidden", "src/main.ts")
    assert (escaping.status, escaping.reason) == ("ambiguous", "path_outside_repository")
    assert edge(graph, "call", "secret", "src/main.ts").status == "ambiguous"


def test_cpp_competing_header_paths_and_dynamic_include():
    graph = analyze_dependencies([
        parse(cpp, "base.hpp", "class Base {};\n"),
        parse(cpp, "src/base.hpp", "class Base {};\n"),
        parse(cpp, "src/main.cpp", '#include "base.hpp"\n#include HEADER\nclass Child : public Base {};\n'),
    ])
    assert edge(graph, "import", "base.hpp", "src/main.cpp").status == "ambiguous"
    dynamic = edge(graph, "import", "HEADER", "src/main.cpp")
    assert (dynamic.status, dynamic.reason) == ("ambiguous", "dynamic_include")
    assert edge(graph, "inheritance", "Base", "src/main.cpp").status == "ambiguous"


def test_ordinary_unrelated_same_name_does_not_create_a_call():
    graph = analyze_dependencies([
        parse(python, "caller.py", "def run():\n    work()\n"),
        parse(python, "a.py", "def work(): pass\n"),
        parse(python, "b.py", "def work(): pass\n"),
    ])
    unresolved = edge(graph, "call", "work", "caller.py")
    assert unresolved.status == "ambiguous" and unresolved.target is None


def test_external_imports_and_multi_file_namespace_are_not_falsely_resolved():
    graph = analyze_dependencies([
        parse(python, "app.py", "import json\n"),
        parse(csharp, "Lib/One.cs", "namespace Lib; public class One {}"),
        parse(csharp, "Lib/Two.cs", "namespace Lib; public class Two {}"),
        parse(csharp, "App/Main.cs", "using Lib; namespace App; public class Main {}"),
    ])
    assert edge(graph, "import", "json", "app.py").status == "external"
    namespace = edge(graph, "import", "Lib", "App/Main.cs")
    assert namespace.status == "ambiguous"
    assert namespace.candidates == ["file:Lib/One.cs", "file:Lib/Two.cs"]


def test_missing_member_in_known_package_and_missing_include_are_uncertain():
    graph = analyze_dependencies([
        parse(python, "pkg/__init__.py", "def known(): pass\n"),
        parse(python, "consumer.py", "from pkg import missing\n"),
        parse(cpp, "main.cpp", '#include "not-present.hpp"\nvoid run() {}\n'),
    ])
    assert edge(graph, "import", "pkg.missing", "consumer.py").reason == "missing_local_member"
    assert edge(graph, "import", "not-present.hpp", "main.cpp").status == "ambiguous"


def test_python_src_layout_import_and_call():
    graph = analyze_dependencies([
        parse(python, "src/sample/__init__.py", ""),
        parse(python, "src/sample/simple.py", "def add_one(number): return number + 1\n"),
        parse(python, "tests/test_simple.py", "from sample.simple import add_one\nadd_one(1)\n"),
    ])
    assert edge(graph, "import", "sample.simple.add_one", "tests/test_simple.py").target == "file:src/sample/simple.py"
    assert edge(graph, "call", "add_one", "tests/test_simple.py").target == "symbol:src/sample/simple.py:add_one"


def test_python_src_collision_is_ambiguous_but_relative_import_is_anchored():
    graph = analyze_dependencies([
        parse(python, "pkg/util.py", "def work(): pass\n"),
        parse(python, "src/pkg/util.py", "def work(): pass\n"),
        parse(python, "src/pkg/main.py", "from .util import work\nwork()\n"),
        parse(python, "consumer.py", "from pkg.util import work\nwork()\n"),
    ])
    conflict = edge(graph, "import", "pkg.util.work", "consumer.py")
    assert conflict.status == "ambiguous"
    assert conflict.candidates == ["file:pkg/util.py", "file:src/pkg/util.py"]
    assert edge(graph, "call", "work", "consumer.py").target is None
    assert edge(graph, "call", "work", "src/pkg/main.py").target == "symbol:src/pkg/util.py:work"


def test_python_src_namespace_package_and_unrelated_directory():
    graph = analyze_dependencies([
        parse(python, "src/namespace/util.py", "def work(): pass\n"),
        parse(python, "vendor/other/util.py", "def work(): pass\n"),
        parse(python, "main.py", "from namespace.util import work\nimport other.util\nwork()\n"),
    ])
    assert edge(graph, "call", "work", "main.py").target == "symbol:src/namespace/util.py:work"
    assert edge(graph, "import", "other.util", "main.py").status == "external"
