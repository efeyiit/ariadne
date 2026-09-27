import pytest
from app.local import runtime as module
from app.local.importer import UploadedSource, import_files
from app.local.store import LocalStore


@pytest.mark.parametrize('action', ['cancel', 'shutdown'])
def test_cancelled_queued_job_does_not_prepare_source(tmp_path, monkeypatch, action):
    class ManualPool:
        def __init__(self):
            self.pending = []
        def submit(self, fn, *args):
            self.pending.append((fn, args))
        def drain(self):
            while self.pending:
                fn, args = self.pending.pop(0)
                fn(*args)
        def shutdown(self, **kwargs):
            self.drain()
    prepared = []
    def unexpected_preparation(source):
        prepared.append(source.snapshot_id)
        raise AssertionError('Cancelled source should not be prepared')
    monkeypatch.setattr(module, 'material_for', unexpected_preparation)
    store = LocalStore(tmp_path / 'data.sqlite3')
    source = import_files('Example', [UploadedSource(path='main.py', content='x = 1')])
    store.save_snapshot(source)
    runtime = module.LocalRuntime(store)
    runtime._pool.shutdown()
    runtime._pool = ManualPool()
    try:
        job = runtime.analyze(source.repository_id, source.snapshot_id)
        if action == 'cancel':
            runtime.cancel(job.job_id)
            runtime._pool.drain()
        else:
            runtime.close()
        assert prepared == []
        saved = store.load_job(job.job_id)
        assert saved.status == 'cancelled'
        assert saved.error_code is None
        assert saved.analysis_id is None
        assert store.latest_analysis(source.repository_id, source.snapshot_id) is None
        assert not runtime._stop
    finally:
        runtime.close()
