from fastapi.testclient import TestClient

from app.analyzers.dependencies import analyze_dependencies
from app.local.importer import UploadedSource, import_files
from app.local.main import create_local_app
from app.local.store import LocalStore
from app.parsers.python import parse_file


def setup_report(tmp_path):
    source = import_files('Classes', [UploadedSource(path='main.py', content='class Standalone: pass\n')])
    store = LocalStore(tmp_path / 'ariadne.sqlite3')
    store.save_snapshot(source)
    graph = analyze_dependencies([parse_file('main.py', source.sources['main.py'])])
    store.save_analysis('first', source.repository_id, source.snapshot_id, {'dependencies': graph.model_dump()})
    return store, dict(repository_id=source.repository_id, snapshot_id=source.snapshot_id, analysis_id='first')


def test_local_diagrams_include_standalone_classes_and_both_formats(tmp_path):
    _, params = setup_report(tmp_path)
    with TestClient(create_local_app(tmp_path), base_url='http://127.0.0.1') as client:
        assert client.get('/api/local/diagrams', params=params).status_code == 401
        client.get('/api/local/session')
        response = client.get('/api/local/diagrams', params=params)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['analysis_id'] == 'first'
        assert data['snapshot_id'] == params['snapshot_id']
        assert set(data['diagrams']) == {'mermaid', 'plantuml'}
        assert 'Standalone' in data['diagrams']['mermaid']['class_diagram']
        assert 'Standalone' in data['diagrams']['plantuml']['class_diagram']
        assert 'not a runtime trace' in data['diagrams']['mermaid']['sequence_diagram']


def test_diagrams_are_pinned_to_requested_analysis_not_latest(tmp_path):
    store, params = setup_report(tmp_path)
    store.save_analysis('newer', params['repository_id'], params['snapshot_id'], {'dependencies': None})
    other = import_files('Other', [UploadedSource(path='other.py', content='class Other: pass')])
    store.save_snapshot(other)
    store.save_analysis('foreign', other.repository_id, other.snapshot_id, {'dependencies': None})
    with TestClient(create_local_app(tmp_path), base_url='http://127.0.0.1') as client:
        client.get('/api/local/session')
        assert client.get('/api/local/diagrams', params=params).status_code == 200
        assert client.get('/api/local/diagrams', params=params | {'analysis_id': 'foreign'}).status_code == 409
        assert client.get('/api/local/diagrams', params=params | {'analysis_id': 'absent'}).status_code == 404
        assert client.get('/api/local/diagrams', params=params | {'analysis_id': 'newer'}).status_code == 404


def test_diagram_limits_produce_explicit_error(tmp_path):
    store, params = setup_report(tmp_path)
    nodes = [dict(id=f'file:{i}.py', kind='file', language='python', name=f'{i}.py',
                  location=dict(path=f'{i}.py', start_line=1, end_line=1)) for i in range(501)]
    store.save_analysis('oversize', params['repository_id'], params['snapshot_id'],
                        {'dependencies': dict(nodes=nodes, edges=[], cycles=[], critical_nodes=[])})
    with TestClient(create_local_app(tmp_path), base_url='http://127.0.0.1') as client:
        client.get('/api/local/session')
        response = client.get('/api/local/diagrams', params=params | {'analysis_id': 'oversize'})
        assert response.status_code == 422
        assert response.json()['detail'] == 'DIAGRAM_UNAVAILABLE'
