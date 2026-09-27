# Python src-layout dependency resolution

Python imports such as `from sample.simple import add_one` were reported as
external when their implementation lived in `src/sample/simple.py`. The module
index only contained the physical path name `src.sample.simple`.

The resolver now also indexes repository-root `src/` modules by their conventional
import name. Import and callable edges retain the actual source path and lines.
Namespace packages do not require an `__init__.py`. A root module competing with
a `src/` module remains ambiguous; relative imports retain their physical anchor.
Unrelated directories are not promoted to import roots. Repository code is never
executed to discover imports.

Verification on 2026-09-27:

- Three new real-parser regression tests failed before the change, then passed.
- `python -m pytest tests/dependencies tests/parsers -q`: 38 passed.
- `python -m pytest -q`: 349 passed, 37 skipped; existing Starlette warning.
- PostgreSQL-dependent skips are not a successful database integration check.

This is conventional static resolution, not a Python interpreter import trace.
Custom package mappings, arbitrary source roots and dynamic search paths remain
unsupported. Existing stored reports need reanalysis using a restarted backend
to include the new graph; this change does not rewrite historical reports.
