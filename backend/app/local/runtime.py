"""Bounded background analysis over persisted, inert source copies."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha1
from pathlib import PurePosixPath
from threading import Event, Lock
from uuid import uuid4

from app.ai.orchestration.coordinator import Coordinator, SnapshotMaterial
from app.ai.orchestration.worker_adapter import to_analysis_result
from app.local.models import LocalSnapshot, StoredJob
from app.local.store import LocalStore
from app.services.github_public.service import RepositoryFile, RepositorySnapshot, LANGUAGES, GitHubPublicService

PARSED_SUFFIXES = {".py", ".ts", ".tsx", ".mts", ".cts", ".java", ".cs", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"}


def material_for(source: LocalSnapshot) -> SnapshotMaterial:
    files, code, documents, coverage = [], {}, {}, {}
    for path, content in source.sources.items():
        raw = content.encode("utf-8")
        suffix = PurePosixPath(path).suffix.lower()
        included = suffix in PARSED_SUFFIXES
        files.append(RepositoryFile(path, sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
                                    len(raw), LANGUAGES.get(suffix), included,
                                    None if included else "document_or_unsupported_language"))
        if path == "coverage.xml":
            coverage[path] = content
        else:
            (code if included else documents)[path] = content
    snapshot = RepositorySnapshot(repository_id=source.repository_id, github_url=source.github_url or "", name=source.name,
                                  default_branch="", commit_sha=source.commit_sha, tree_sha="",
                                  files=tuple(files), languages=tuple(Counter(f.language for f in files if f.language).items()),
                                  frameworks=(), snapshot_id=source.snapshot_id if source.source_kind == "local" else None)
    return SnapshotMaterial(snapshot=snapshot, sources=code, document_sources=documents, coverage_artifacts=coverage)


class LocalRuntime:
    def __init__(self, store: LocalStore, answer_provider=None):
        self.answer_provider = answer_provider
        self.store = store
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-analysis")
        self._lock = Lock()
        self._stop: dict[str, Event] = {}
        self._closed = False

    def import_github(self, url: str, service=None) -> LocalSnapshot:
        reader = service or GitHubPublicService()
        snapshot = reader.fetch_repository(url)
        sources = {file.path: reader.fetch_file(snapshot, file) for file in snapshot.included_files}
        for file in reader.document_files(snapshot):
            if file.path not in sources:
                sources[file.path] = reader.fetch_document_file(snapshot, file)
        source = LocalSnapshot(repository_id="github-" + str(snapshot.repository_id),
                               snapshot_id="github:" + snapshot.commit_sha, source_kind="github",
                               github_url=snapshot.github_url, commit_sha=snapshot.commit_sha,
                               name=snapshot.name, sources=sources,
                               excluded={file.path: file.exclusion_reason or "not_selected" for file in snapshot.files if file.path not in sources})
        self.store.save_snapshot(source)
        return source

    def analyze(self, repository_id: str, snapshot_id: str, *, force=False, language="en") -> StoredJob:
        if language not in ("en", "tr"):
            raise ValueError("Unsupported report language")
        with self._lock:
            if self._closed:
                raise ValueError("runtime is closed")
            existing = self.store.latest_job(repository_id, snapshot_id)
            if existing is not None and (existing.status in ("queued", "running") or (not force and existing.status not in ("failed", "cancelled"))):
                return existing
            if sum(self.store.load_job(job_id).status in ("queued", "running")
                   for job_id in self._stop) >= 8:
                raise ValueError("analysis queue is full")
            source = self.store.load_snapshot(repository_id, snapshot_id)
            if source is None:
                raise KeyError("snapshot not found")
            job = StoredJob(job_id=str(uuid4()), repository_id=repository_id, snapshot_id=snapshot_id, status="queued")
            self.store.save_job(job)
            self._stop[job.job_id] = Event()
            try:
                self._pool.submit(self._run, job, source, self._stop[job.job_id], language)
            except Exception:
                self._stop.pop(job.job_id, None)
                job.status = "failed"
                job.error_code = "ANALYSIS_FAILED"
                self.store.save_job(job)
                raise
            return job

    def _run(self, job: StoredJob, source: LocalSnapshot, stop: Event, language="en") -> None:
        try:
            with self._lock:
                if stop.is_set():
                    job.status = "cancelled"
                    self.store.save_job(job)
                    self._stop.pop(job.job_id, None)
                    return
                job.status = "running"
                self.store.save_job(job)
            material = material_for(source)
            coordinator = Coordinator(lambda owner, repo: material.snapshot if repo == source.repository_id else None,
                                      max_bytes=20 * 1024 * 1024)
            report = coordinator.run("local", material, should_stop=stop.is_set)
            from app.local.review import build_review
            result = to_analysis_result(report, str(uuid4()))
            payload = result.model_dump(mode="json")
            payload["review"] = build_review(source, payload, language=language, provider=self.answer_provider, should_stop=stop.is_set)
            with self._lock:
                if stop.is_set():
                    job.status = "cancelled"
                else:
                    self.store.save_analysis(result.analysis_id, source.repository_id, source.snapshot_id,
                                             payload)
                    job.status = report.status
                    job.analysis_id = result.analysis_id
                self.store.save_job(job)
                self._stop.pop(job.job_id, None)
        except Exception:
            with self._lock:
                job.status = "cancelled" if stop.is_set() else "failed"
                job.error_code = None if stop.is_set() else "ANALYSIS_FAILED"
                try:
                    self.store.save_job(job)
                finally:
                    self._stop.pop(job.job_id, None)

    def cancel(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._stop:
                self._stop[job_id].set()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for stop in self._stop.values():
                stop.set()
        self._pool.shutdown(wait=True)
