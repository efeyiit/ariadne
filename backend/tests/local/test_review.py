from time import monotonic, sleep
from app.local.importer import UploadedSource, import_files
from app.local.runtime import LocalRuntime
from app.local.store import LocalStore


def test_explicit_reanalysis_produces_a_new_report_in_selected_language(tmp_path):
    store = LocalStore(tmp_path / 'db.sqlite')
    source = import_files('Parcel', [UploadedSource(path='main.py', content='def main():\n    print("Parcel ready")\n'), UploadedSource(path='README.md', content='# Parcel\nA parcel tracking command line tool.\n')])
    store.save_snapshot(source)
    runtime = LocalRuntime(store)
    def finish(job):
        deadline = monotonic() + 10
        while store.load_job(job.job_id).status in ('queued', 'running') and monotonic() < deadline:
            sleep(.02)
        result = store.load_job(job.job_id)
        assert result.status == 'succeeded', result
        return store.load_analysis(result.analysis_id)['report']
    try:
        first = runtime.analyze(source.repository_id, source.snapshot_id)
        old = finish(first)
        second = runtime.analyze(source.repository_id, source.snapshot_id, force=True, language='tr')
        new = finish(second)
        assert second.job_id != first.job_id
        assert new['analysis_id'] != old['analysis_id']
        assert new['review']['language'] == 'tr'
        assert new['review']['version'] == 1
        assert new['review']['ai_status'] == 'unavailable'
        assert new['review']['entry_points'][0]['path'] == 'main.py'
        assert new['review']['modules']
        assert new['review']['scope']['source_files'] == 2
        assert store.load_analysis(old['analysis_id']) is not None
    finally:
        runtime.close()

def test_review_rejects_fabricated_quotes_and_keeps_static_report():
    from app.local.review import build_review
    source = import_files('Example', [UploadedSource(path='README.md', content='A parcel tracker.')])
    class BadProvider:
        def answer(self, prompt):
            return {'claims': [{'text': 'Invented', 'citations': [{'evidence_id': 'E1', 'start_line': 1, 'end_line': 1, 'quote': 'not in source'}]}]}
    review = build_review(source, {'findings': []}, language='tr', provider=BadProvider())
    assert review['purpose']['status'] == 'rejected'
    assert review['purpose']['claims'] == []
    assert review['priorities'] == []


def test_priorities_follow_severity_and_do_not_expose_raw_findings():
    from app.local.review import build_review
    source = import_files('Example', [UploadedSource(path='main.py', content='x = 1')])
    findings = [{'id': level, 'severity': level, 'issue_type': 'hardcoded_secret', 'description': 'private-value', 'location': {'path': 'main.py', 'start_line': 1, 'end_line': 1}} for level in ('low', 'high', 'medium')]
    review = build_review(source, {'findings': findings})
    assert [p['severity'] for p in review['priorities']] == ['high', 'medium', 'low']
    assert 'private-value' not in str(review)


def test_model_failure_does_not_destroy_static_results():
    from app.local.review import build_review
    source = import_files('Example', [UploadedSource(path='README.md', content='A parcel tracker.')])
    class Offline:
        def answer(self, prompt):
            raise ConnectionError('offline')
    result = build_review(source, {'findings': []}, provider=Offline())
    assert result['purpose']['status'] == 'unavailable'
    assert result['scope']['source_files'] == 1

def test_forced_requests_share_an_active_job(tmp_path):
    class HeldPool:
        def submit(self, *args): pass
        def shutdown(self, **kwargs): pass
    store = LocalStore(tmp_path / 'jobs.sqlite')
    source = import_files('Example', [UploadedSource(path='main.py', content='x = 1')])
    store.save_snapshot(source)
    runtime = LocalRuntime(store)
    runtime._pool.shutdown()
    runtime._pool = HeldPool()
    try:
        first = runtime.analyze(source.repository_id, source.snapshot_id, force=True)
        second = runtime.analyze(source.repository_id, source.snapshot_id, force=True)
        assert second.job_id == first.job_id
    finally:
        runtime.close()


def test_review_ai_receives_the_requested_language_and_cancel_stops_calls():
    from app.local.review import build_review
    source = import_files('Example', [UploadedSource(path='README.md', content='A parcel tracker.')])
    prompts = []
    class Provider:
        def answer(self, prompt):
            prompts.append(prompt.question)
            return {'claims': []}
    build_review(source, {'findings': []}, language='tr', provider=Provider())
    assert 'Bu belgeye' in prompts[0]
    build_review(source, {'findings': []}, provider=Provider(), should_stop=lambda: True)
    assert len(prompts) == 1

def test_test_fixture_numbers_remain_findings_but_not_priority_work():
    from app.local.review import build_review
    source = import_files('Example', [UploadedSource(path='tests/test_math.py', content='assert 5 + 1 == 6')])
    report = {'findings':[{'id':'one','severity':'medium','issue_type':'magic_number','location':{'path':'tests/test_math.py','start_line':1,'end_line':1}}]}
    result = build_review(source, report)
    assert result['scope']['total_findings'] == 1
    assert result['priorities'] == []

def test_simple_code_explanations_do_not_ask_model_to_invent_arithmetic():
    from app.local.review import source_explanation
    source = import_files('Math', [UploadedSource(path='math.py',content='def add_one(number):\n    return number + 1\n'), UploadedSource(path='main.py', content='def main():\n    print("Call your application here")\n')])
    explanation = source_explanation(source, 'math.py', 'tr')
    assert explanation['status'] == 'static'
    assert 'number + 1' in explanation['claims'][0]['text']
    assert explanation['claims'][0]['citations'][0]['quote'] == '    return number + 1'
    main = source_explanation(source, 'main.py', 'tr')
    assert 'yazdırır' in main['claims'][0]['text']
    assert 'çağırır' not in main['claims'][0]['text']


def test_nontrivial_source_is_not_presented_as_a_simple_expression():
    from app.local.review import source_explanation
    source = import_files('Math', [UploadedSource(path='main.py', content='def main():\n    dangerous()\n    return 1\n')])
    assert source_explanation(source, 'main.py', 'en') is None
