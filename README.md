# Ariadne

Ariadne explores a codebase through its architecture, dependencies, code quality, tests, security findings, and source-linked explanations. Its name comes from Ariadne's thread through the labyrinth: every finding should lead back to the code behind it.

## Run locally

The local workspace requires no account, GitHub OAuth app, PostgreSQL server, or cloud AI key. Import a public GitHub URL or select a local source folder, including a locally cloned private repository.

Install Python dependencies from `backend/`:

```sh
uv sync
```

Install and build the interface from `frontend/`:

```sh
pnpm install --frozen-lockfile
pnpm build
```

Start from `backend/`:

```sh
uv run python -m app.local.launcher
```

Open **http://127.0.0.1:8080**. Stop with Ctrl+C. The service listens on loopback only; this is a single-user local workspace, not a hosted public service.

## Explore a repository

- **Public GitHub:** paste a repository URL. Sources are fetched at a real commit; GitHub's unauthenticated API limits apply.
- **Local/private:** choose the project folder. Selected text files are copied into local storage; the original files are never executed or changed. Common secret files and generated directories are excluded. Review your selection: filtering cannot identify every secret.
- Run analysis for architecture, dependencies, security observations, testing observations, refactoring candidates, and documentation drafts. Follow findings to the saved source lines or export the complete report.
- The Overview review connects project purpose, source-linked module explanations, prioritized findings and a dependency diagram. Use **Analyze snapshot** to generate a fresh report; previous results are preserved.
- Choose **English** or **Türkçe** in the header. English is the default; the preference is saved on this browser. New report explanations use the selected language.
- Reports and source snapshots survive restarts. Reimporting changed files creates a new content identity; old source links stay pinned to their original snapshot.

Local imports allow up to 2,000 selected files, 1 MiB per file, and 20 MiB total text. Parsing covers Python, TypeScript/TSX, Java, C#, and C++; other supported text can provide documentation context. Analysis is static: test detection is not test execution, and absence of findings does not establish correctness or security.

Data is stored under `storage/local/` (SQLite and optional embedded Qdrant). Set `ARIADNE_LOCAL_DATA` to choose another data directory. The storage directory is excluded from Git.

## Optional local AI

Static analysis works without a model. If the model environment and cached weights described in [local model setup](training/LOCAL-RUNTIME.md) are already installed, start with:

```sh
uv run python -m app.local.launcher --with-ai
```

The launcher does not download models. AI chat combines semantic search with source-name and symbol matching inside the selected repository snapshot. Focused questions use one excerpt; flow questions can use up to four files, including resolved dependencies when a saved analysis is available. The interface shows which excerpts reached the model and links each answer's citations to saved source lines. Broad questions may still need more context. See the [multi-file evaluation](docs/evidence/2026-09-27-multifile-ai.md) for verified examples and limits. Unavailable, unsupported and rejected answers remain explicit. Citation validation checks source correspondence; it does not guarantee that a model's interpretation is correct.

## Verification and alternate server mode

See the [local acceptance record](docs/evidence/2026-09-25-local-workspace.md) for actual checks and limitations. Run `uv run pytest -q` in `backend/`, and `pnpm test` / `pnpm build` in `frontend/`.

The separate [authenticated server setup](deployment/local-app/README.md) retains PostgreSQL, HTTPS, and GitHub OAuth integration. Those prerequisites are not needed for the local workspace. The [roadmap](docs/product-roadmap.md) and [source design](docs/source-design.md) describe broader capabilities; they are not claims that every planned feature has been delivered.
