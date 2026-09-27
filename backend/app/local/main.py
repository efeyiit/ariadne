"""Loopback application: no OAuth account or PostgreSQL service required."""

from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Literal
from secrets import token_urlsafe

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from app.contracts.analysis import WireModel
from app.local.importer import ImportLimits, UploadedSource, import_files
from app.local.runtime import LocalRuntime
from app.local.security import LocalBoundary
from app.local.store import LocalStore
from app.services.github_public.service import GitHubPublicError


class FolderInput(WireModel):
    name: str = Field(min_length=1, max_length=200)
    files: list[UploadedSource] = Field(max_length=2000)
    repository_id: str | None = None


class GitHubInput(WireModel):
    github_url: str = Field(min_length=1, max_length=300)


class SnapshotInput(WireModel):
    repository_id: str = Field(min_length=1, max_length=200)
    snapshot_id: str = Field(min_length=1, max_length=100)


class AnalyzeInput(SnapshotInput):
    force: bool = False
    language: Literal["en", "tr"] = "en"


class ChatInput(SnapshotInput):
    question: str = Field(min_length=1, max_length=1000)


def create_local_app(data_dir: Path, *, max_body_bytes: int = 30 * 1024 * 1024) -> FastAPI:
    data_dir = Path(data_dir)
    store = LocalStore(data_dir / "ariadne.sqlite3")
    session, csrf = token_urlsafe(32), token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        # Hold an OS lock for the entire runtime; a second instance must not recover live jobs.
        lock = (data_dir / "instance.lock").open("a+b")
        lock.seek(0)
        if lock.read(1) == b"":
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            import os
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            store.recover_interrupted_jobs()
            app.state.runtime = LocalRuntime(store)
            app.state.retrieval = None
            if os.environ.get("ARIADNE_LOCAL_RUNTIME_TOKEN"):
                from app.local.retrieval import LocalRetrieval
                from app.local_inference.provider import LocalAnswerProvider, LocalEmbeddingProvider
                try:
                    app.state.retrieval = LocalRetrieval(data_dir / "vectors", store, LocalEmbeddingProvider(), LocalAnswerProvider())
                    app.state.runtime.answer_provider = app.state.retrieval.provider
                except Exception:
                    # Optional indexing must never prevent static analysis from opening.
                    app.state.retrieval = None
            try:
                yield
            finally:
                app.state.runtime.close()
                if app.state.retrieval is not None:
                    app.state.retrieval.close()
        finally:
            lock.close()

    app = FastAPI(title="Ariadne Local", lifespan=lifespan)
    app.add_middleware(LocalBoundary, session=session, csrf=csrf, max_body_bytes=max_body_bytes)

    @app.exception_handler(ValueError)
    async def invalid_input(request, exc):
        return JSONResponse({"detail": "INVALID_INPUT", "message": str(exc)}, status_code=400)

    @app.exception_handler(GitHubPublicError)
    async def github_error(request, exc):
        return JSONResponse({"detail": exc.code, "message": str(exc)}, status_code=502)

    @app.get("/api/runtime")
    def runtime_mode():
        return {"mode": "local", "ai_status": "unavailable", "limits": asdict(ImportLimits())}

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": "local"}

    @app.get("/api/local/session")
    def bootstrap():
        response = JSONResponse({"csrf_token": csrf, "limits": asdict(ImportLimits())}, headers={"Cache-Control": "no-store"})
        response.set_cookie("ariadne_local", session, httponly=True, samesite="strict", path="/")
        return response

    @app.get("/api/local/repositories")
    def repositories():
        return store.list_repositories()

    @app.get("/api/local/ai")
    def ai_status():
        if app.state.retrieval is None:
            return {"status": "unavailable"}
        from app.local_inference.provider import runtime_health
        try:
            runtime_health()
            return {"status": "ready"}
        except Exception:
            return {"status": "unavailable"}

    @app.post("/api/local/chat")
    def chat(body: ChatInput):
        get_source(body.repository_id, body.snapshot_id)
        if app.state.retrieval is None:
            return {"status": "unavailable", "answer": "Local AI is not connected. Static analysis remains usable.", "claims": [], "snapshot_id": body.snapshot_id}
        return app.state.retrieval.ask(body.repository_id, body.snapshot_id, body.question)

    @app.post("/api/local/import")
    def folder(body: FolderInput):
        source = import_files(body.name, body.files, repository_id=body.repository_id)
        store.save_snapshot(source)
        return source.model_dump(exclude={"sources"})

    @app.post("/api/local/github")
    def github(body: GitHubInput):
        return app.state.runtime.import_github(body.github_url).model_dump(exclude={"sources"})

    def get_source(repository_id: str, snapshot_id: str):
        source = store.load_snapshot(repository_id, snapshot_id)
        if source is None:
            raise HTTPException(404, "SNAPSHOT_NOT_FOUND")
        return source

    @app.get("/api/local/files")
    def files(repository_id: str, snapshot_id: str):
        source = get_source(repository_id, snapshot_id)
        return {"files": sorted(source.sources), "excluded": source.excluded}

    @app.get("/api/local/source")
    def source(repository_id: str, snapshot_id: str, path: str):
        saved = get_source(repository_id, snapshot_id)
        if path not in saved.sources:
            raise HTTPException(404, "SOURCE_NOT_FOUND")
        return JSONResponse({"path": path, "content": saved.sources[path], "snapshot_id": snapshot_id}, headers={"Cache-Control": "no-store"})

    @app.post("/api/local/analyze")
    def analyze(body: AnalyzeInput):
        get_source(body.repository_id, body.snapshot_id)
        return app.state.runtime.analyze(body.repository_id, body.snapshot_id, force=body.force, language=body.language)

    @app.get("/api/local/jobs/{job_id}")
    def job(job_id: str):
        result = store.load_job(job_id)
        if result is None:
            raise HTTPException(404, "JOB_NOT_FOUND")
        return result

    @app.post("/api/local/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        job(job_id)
        app.state.runtime.cancel(job_id)
        return {"status": "requested"}

    @app.get("/api/local/report")
    def report(repository_id: str, snapshot_id: str):
        get_source(repository_id, snapshot_id)
        return store.latest_analysis(repository_id, snapshot_id)

    @app.get("/api/local/export")
    def export(repository_id: str, snapshot_id: str):
        result = report(repository_id, snapshot_id)
        if result is None:
            raise HTTPException(404, "REPORT_NOT_FOUND")
        return JSONResponse(result["report"], headers={"Content-Disposition": 'attachment; filename="ariadne-analysis.json"', "Cache-Control": "no-store"})

    frontend = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if frontend.is_dir():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")
        if (frontend / "brand").is_dir():
            app.mount("/brand", StaticFiles(directory=frontend / "brand"), name="brand")

        @app.get("/{path:path}")
        def index(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            return FileResponse(frontend / "index.html", headers={"Cache-Control": "no-store"})
    return app


def main():
    import os
    import uvicorn
    root = Path(__file__).resolve().parents[3]
    app = create_local_app(Path(os.environ.get("ARIADNE_LOCAL_DATA", str(root / "storage" / "local"))))
    uvicorn.run(app, host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
