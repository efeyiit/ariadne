"""Run the real HTTPS API, queue worker and local model as owned child processes."""

from __future__ import annotations

import json
from hashlib import sha256
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import psycopg

from app.cache import apply_cache_schema
from app.database import apply_schema
from app.jobs import apply_jobs_schema
from app.security.identity import apply_identity_schema
from app.security.identity.http import build_identity_http_from_env


ROOT = Path(__file__).resolve().parents[3]
MODEL_ID = "intfloat/multilingual-e5-small"
ANSWER_MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
PROMPT_VERSION = "shared-passage-selection-v5"


def _free(port: int) -> None:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"127.0.0.1:{port} is already in use") from exc


def _frontend() -> Path:
    frontend = ROOT / "frontend"
    built = frontend / "dist" / "index.html"
    sources = [frontend / "index.html", frontend / "package.json", frontend / "pnpm-lock.yaml",
               frontend / "tsconfig.json", frontend / "vite.config.ts"]
    for directory in ("src", "public"):
        if (frontend / directory).is_dir():
            sources.extend(p for p in (frontend / directory).rglob("*") if p.is_file())
    if built.is_file() and all(not p.is_file() or p.stat().st_mtime <= built.stat().st_mtime for p in sources):
        return built.parent
    build_env = {key: value for key, value in os.environ.items()
                 if not key.startswith("ARIADNE_")}
    node = shutil.which("node") or str(Path.home() / ".cache" / "codex-runtimes" /
        "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe")
    for script, args in (("typescript/bin/tsc", ["--noEmit"]),
                         ("vite/bin/vite.js", ["build"])):
        target = frontend / "node_modules" / script
        if not Path(node).is_file() or not target.is_file():
            raise RuntimeError("Frontend build dependencies are missing")
        subprocess.run([node, str(target), *args], cwd=frontend, env=build_env, check=True)
    if not built.is_file():
        raise RuntimeError("Frontend build did not produce index.html")
    return built.parent


def _preflight() -> None:
    for name in ("ARIADNE_DATABASE_URL", "ARIADNE_GITHUB_CLIENT_ID",
                 "ARIADNE_GITHUB_CLIENT_SECRET", "ARIADNE_GITHUB_REDIRECT_URI",
                 "ARIADNE_OAUTH_FERNET_KEYS", "ARIADNE_LOCAL_TLS_CERT",
                 "ARIADNE_LOCAL_TLS_KEY", "ARIADNE_LOCAL_TLS_CA",
                 "ARIADNE_QDRANT_API_KEY_FILE"):
        if not os.getenv(name):
            raise RuntimeError(f"Missing required setting: {name}")
    with psycopg.connect(os.environ["ARIADNE_DATABASE_URL"], autocommit=True, connect_timeout=5) as conn:
        with conn.transaction():
            apply_schema(conn)
            apply_identity_schema(conn)
            apply_jobs_schema(conn)
            apply_cache_schema(conn)
    identity = build_identity_http_from_env()
    identity.close()
    with urlopen("http://127.0.0.1:6333/readyz", timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("Qdrant is not ready")
    _free(8767)
    _free(8443)


def _start(args: list[str], cwd: Path, env: dict[str, str], log: Path) -> subprocess.Popen:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as output:
        return subprocess.Popen(args, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)


def _ready_model(model: subprocess.Popen, source: Path) -> None:
    deadline = monotonic() + 360
    expected_hash = sha256(source.read_bytes()).hexdigest()
    while monotonic() < deadline:
        if model.poll() is not None:
            raise RuntimeError("Local E5 model worker stopped during startup")
        try:
            with urlopen("http://127.0.0.1:8767/health", timeout=2) as response:
                data = json.loads(response.read(4096))
            if data.get("status") == "ready":
                if (data.get("embedding_model_id") != MODEL_ID or
                        data.get("model_id") != ANSWER_MODEL_ID or
                        data.get("runtime_code_sha256") != expected_hash or
                        data.get("prompt_version") != PROMPT_VERSION):
                    raise RuntimeError("Local model worker has the wrong runtime fingerprint")
                return
        except (OSError, ValueError, URLError):
            pass
        sleep(1)
    raise RuntimeError("Local E5 model worker did not become ready within six minutes")


def _ready_site(site: subprocess.Popen, ca: str) -> None:
    context = ssl.create_default_context(cafile=ca)
    deadline = monotonic() + 60
    while monotonic() < deadline:
        if site.poll() is not None:
            raise RuntimeError("HTTPS product site stopped during startup")
        try:
            with urlopen("https://localhost:8443/health", context=context, timeout=2) as response:
                if response.status != 200:
                    raise RuntimeError("Product health check failed")
            try:
                urlopen("https://localhost:8443/auth/me", context=context, timeout=2)
            except HTTPError as exc:
                if exc.code == 401:
                    return
                raise RuntimeError(f"Product identity is unavailable (HTTP {exc.code})") from exc
        except (OSError, URLError):
            pass
        sleep(1)
    raise RuntimeError("HTTPS product site did not become ready within one minute")


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def main() -> None:
    control = Path(os.path.abspath(os.environ["ARIADNE_LOCAL_CONTROL_DIR"]))
    subprocess.run(["pwsh.exe", "-NoProfile", "-File",
                    str(ROOT / "deployment" / "local-app" / "assert-control.ps1"),
                    "-ControlDir", str(control)], check=True, capture_output=True, text=True)
    _preflight()
    frontend = _frontend()
    model_python = ROOT / "training" / ".venv" / "Scripts" / "python.exe"
    model_script = ROOT / "training" / "local_runtime_server.py"
    if not model_python.is_file() or not model_script.is_file():
        raise RuntimeError("Pinned local E5 model runtime is missing")
    run_id = secrets.token_urlsafe(16)
    token = secrets.token_urlsafe(32)
    qdrant_key = Path(os.environ["ARIADNE_QDRANT_API_KEY_FILE"]).read_text(encoding="ascii")
    if not re.fullmatch(r"[0-9a-f]{64}", qdrant_key):
        raise RuntimeError("Local Qdrant API key file is invalid")
    children = os.environ.copy()
    children.update({"ARIADNE_LOCAL_RUNTIME_TOKEN": token,
                     "ARIADNE_LOCAL_RUNTIME_URL": "http://127.0.0.1:8767",
                     "ARIADNE_QDRANT_URL": "http://127.0.0.1:6333",
                     "ARIADNE_QDRANT_API_KEY": qdrant_key,
                     "ARIADNE_FRONTEND_DIST": str(frontend)})
    children.pop("ARIADNE_QDRANT_API_KEY_FILE", None)
    model_env = {key: value for key, value in os.environ.items()
                 if not key.startswith("ARIADNE_")}
    model_env.update({"ARIADNE_LOCAL_RUNTIME_TOKEN": token,
                      "ARIADNE_LOCAL_RUNTIME_PORT": "8767"})
    model = _start([str(model_python), str(model_script)], ROOT / "training", model_env,
                   control / "model.log")
    site = worker = None
    state = control / "state.json"
    try:
        _ready_model(model, model_script)
        site = _start([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                       "--port", "8443", "--ssl-keyfile", os.environ["ARIADNE_LOCAL_TLS_KEY"],
                       "--ssl-certfile", os.environ["ARIADNE_LOCAL_TLS_CERT"],
                       "--no-access-log", "--no-proxy-headers"], ROOT / "backend", children,
                      control / "site.log")
        _ready_site(site, os.environ["ARIADNE_LOCAL_TLS_CA"])
        worker = _start([sys.executable, "-m", "app.api.worker"], ROOT / "backend", children,
                        control / "worker.log")
        sleep(2)
        if worker.poll() is not None:
            raise RuntimeError("Analysis worker stopped during startup")
        state.write_text(json.dumps({"run_id": run_id, "launcher_pid": os.getpid(),
                                     "model_pid": model.pid, "site_pid": site.pid,
                                     "worker_pid": worker.pid}), encoding="utf-8")
        while all(p.poll() is None for p in (model, site, worker)):
            request = control / "stop.json"
            try:
                if json.loads(request.read_text(encoding="utf-8")).get("run_id") == run_id:
                    break
            except (OSError, ValueError):
                pass
            sleep(1)
        else:
            raise RuntimeError("Ariadne child process stopped unexpectedly")
    finally:
        for process in (worker, site, model):
            if process is not None:
                _stop(process)
        state.unlink(missing_ok=True)
        request = control / "stop.json"
        try:
            if json.loads(request.read_text(encoding="utf-8")).get("run_id") == run_id:
                request.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    main()
