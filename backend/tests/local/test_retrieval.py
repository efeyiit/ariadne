import pytest

from app.local.importer import UploadedSource, import_files
from app.local.retrieval import LocalRetrieval
from app.local.store import LocalStore


class Vectors:
    model_id = "test-only"
    dimension = 2
    execution_location = "local"
    def embed_documents(self, texts):
        return [[1., 0.] for _ in texts]
    def embed_query(self, text):
        return [1., 0.]


def test_persistent_search_is_scoped_by_repository_and_snapshot(tmp_path):
    store = LocalStore(tmp_path / "data.sqlite3")
    old = import_files("one", [UploadedSource(path="main.py", content="old source")])
    new = import_files("one", [UploadedSource(path="main.py", content="new source")], repository_id=old.repository_id)
    other = import_files("two", [UploadedSource(path="secret.py", content="other repository")])
    for source in (old, new, other):
        store.save_snapshot(source)
    index = LocalRetrieval(tmp_path / "vectors", store, Vectors())
    for source in (old, new, other):
        index.index_snapshot(source.repository_id, source.snapshot_id)
    index.close()
    reopened = LocalRetrieval(tmp_path / "vectors", store, Vectors())
    try:
        hits = reopened.search(new.repository_id, new.snapshot_id, "source")
        assert [hit["text"] for hit in hits] == ["new source"]
        assert reopened.search(old.repository_id, old.snapshot_id, "source")[0]["text"] == "old source"
        with pytest.raises(KeyError):
            reopened.search("missing", new.snapshot_id, "source")
        with pytest.raises(Exception):
            LocalRetrieval(tmp_path / "vectors", store, Vectors())
    finally:
        reopened.close()


def test_model_absence_never_fabricates_answer(tmp_path):
    store = LocalStore(tmp_path / "data.sqlite3")
    source = import_files("one", [UploadedSource(path="main.py", content="print('hello')")])
    store.save_snapshot(source)
    index = LocalRetrieval(tmp_path / "vectors", store, Vectors())
    try:
        assert index.ask(source.repository_id, source.snapshot_id, "Explain this file")["status"] == "unavailable"
    finally:
        index.close()


@pytest.mark.parametrize("quote,expected", [("return 'hello'", "answered"), ("invented quote", "rejected")])
def test_citations_must_match_exact_source(tmp_path, quote, expected):
    class Answers:
        execution_location = "local"
        def answer(self, prompt):
            return {"claims": [{"text": "The function returns hello.", "citations": [{"evidence_id": prompt.evidence[0].id,
                "start_line": 2, "end_line": 2, "quote": quote}]}]}
    store = LocalStore(tmp_path / "data.sqlite3")
    source = import_files("one", [UploadedSource(path="main.py", content="def greet():\n    return 'hello'")])
    store.save_snapshot(source)
    index = LocalRetrieval(tmp_path / "vectors", store, Vectors(), Answers())
    try:
        assert index.ask(source.repository_id, source.snapshot_id, "What does greet return?")["status"] == expected
    finally:
        index.close()

def test_answer_receives_best_ranked_source_without_distracting_neighbors(tmp_path):
    class RankedVectors(Vectors):
        def embed_documents(self, texts):
            return [[1., 0.] if 'def add_one' in text else [0., 1.] for text in texts]
    class Answers:
        execution_location = 'local'
        def answer(self, prompt):
            assert len(prompt.evidence) == 1
            assert prompt.evidence[0].path == 'simple.py'
            return {'claims': []}
    store = LocalStore(tmp_path / 'data.sqlite3')
    source = import_files('one', [UploadedSource(path='simple.py', content='def add_one(n):\n    return n + 1'), UploadedSource(path='README.md',content='Unrelated installation instructions')])
    store.save_snapshot(source)
    index = LocalRetrieval(tmp_path / 'vectors', store, RankedVectors(), Answers())
    try:
        result = index.ask(source.repository_id, source.snapshot_id, 'What does add_one return?')
        assert result['status'] == 'no_evidence'
    finally:
        index.close()


def test_exact_symbol_match_beats_dense_distractor(tmp_path):
    class MisleadingVectors(Vectors):
        def embed_documents(self, texts):
            return [[0., 1.] if 'def persist_invoice' in text else [1., 0.] for text in texts]
    store = LocalStore(tmp_path / 'db.sqlite')
    source = import_files('ranking', [
        UploadedSource(path='storage.py', content='def persist_invoice(invoice):\n    return invoice.id'),
        UploadedSource(path='README.md', content='This project stores invoices using a storage helper.'),
    ])
    store.save_snapshot(source)
    index = LocalRetrieval(tmp_path / 'vectors', store, MisleadingVectors())
    try:
        index.index_snapshot(source.repository_id, source.snapshot_id)
        assert index.search(source.repository_id, source.snapshot_id, 'What does persist_invoice return?')[0]['path'] == 'storage.py'
    finally:
        index.close()


def test_cross_file_question_supplies_distinct_named_files_and_validates_all_citations(tmp_path):
    received = []
    class Answers:
        execution_location = 'local'
        def answer(self, prompt):
            received.extend(prompt.evidence)
            return {'claims': [{'text': 'The two modules define the flow.', 'citations': [
                {'evidence_id': item.id, 'start_line': item.start_line, 'end_line': item.end_line, 'quote': item.text}
                for item in prompt.evidence]}]}
    store = LocalStore(tmp_path / 'db.sqlite')
    source = import_files('flow', [UploadedSource(path='api.py', content='from service import checkout'),
                                  UploadedSource(path='service.py', content='def checkout(): return 1'),
                                  UploadedSource(path='noise.py', content='x = 1')])
    store.save_snapshot(source)
    index = LocalRetrieval(tmp_path / 'vectors', store, Vectors(), Answers())
    try:
        result = index.ask(source.repository_id, source.snapshot_id, 'Explain the flow between api.py and service.py')
        assert result['status'] == 'answered'
        assert {item.path for item in received} == {'api.py', 'service.py'}
        assert {c['path'] for c in result['claims'][0]['citations']} == {'api.py', 'service.py'}
    finally:
        index.close()


def test_context_budget_preserves_complete_lines_and_late_matching_symbol():
    from app.local.search import select_evidence
    hits = [{'path':'big.py','start_line':1,'end_line':48,
             'text':'\n'.join(['# filler'] * 40 + ['def targeted_symbol():', '    return 1'] + ['# tail'] * 6)}]
    selected = select_evidence(hits, 'What does targeted_symbol return?', 'local:' + 'a' * 64)
    assert 'def targeted_symbol():' in selected[0].text
    assert len(selected[0].text.splitlines()) == selected[0].end_line - selected[0].start_line + 1
    many = [dict(hits[0],path=f'{i}.py',text=('x = 1\n' * 48).rstrip()) for i in range(20)]
    context = select_evidence(many, 'Explain the flow across these files', 'local:' + 'a' * 64)
    assert len(context) <= 4
    assert sum(len(item.text) for item in context) <= 6000


def test_related_context_can_recover_a_dependency_outside_semantic_candidates():
    from app.local.search import expand_related
    graph = {'nodes': [
        {'id':'a','location':{'path':'api.py','start_line':1}},
        {'id':'b','location':{'path':'service.py','start_line':40}}],
        'edges':[{'source':'a','target':'b','status':'resolved','kind':'call','location':{'start_line':3}}]}
    api = {'path':'api.py','start_line':1,'end_line':10,'text':'checkout()'}
    service = {'path':'service.py','start_line':35,'end_line':50,'text':'def checkout(): pass'}
    assert expand_related([api],graph,'Trace checkout flow',inventory=[api,service])[1] == service
    graph['edges'][0]['status']='ambiguous'
    assert expand_related([api],graph,'Trace checkout flow',inventory=[api,service]) == [api]
