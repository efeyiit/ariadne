import pytest

from app.ai.orchestration.coordinator import Coordinator
from app.local.importer import UploadedSource, import_files
from app.local.runtime import material_for


def analyze(files):
    source = import_files('Coverage', [UploadedSource(path=p, content=c) for p, c in files.items()])
    material = material_for(source)
    return material, Coordinator(lambda owner, repo: material.snapshot).run('local', material)


def test_imported_coverage_reaches_testing_role_without_document_overlap():
    xml = '<coverage lines-covered="3" lines-valid="4" line-rate="0.75"/>'
    material, report = analyze({'main.py': 'x = 1\n', 'coverage.xml': xml, 'config.xml': '<config/>'})
    assert material.coverage_artifacts == {'coverage.xml': xml}
    assert 'coverage.xml' not in material.document_sources
    assert material.document_sources['config.xml'] == '<config/>'
    assert report.testing.coverage_status == 'available'
    assert report.testing.coverage.percent == 75


def test_missing_coverage_does_not_invent_a_percentage():
    _, report = analyze({'main.py': 'x = 1\n'})
    assert report.testing.coverage is None


@pytest.mark.parametrize('xml', [
    '<broken',
    '<!DOCTYPE x [<!ENTITY x SYSTEM "file:///nonexistent">]><coverage lines-covered="1" lines-valid="1"/>',
])
def test_invalid_coverage_remains_unavailable(xml):
    _, report = analyze({'main.py': 'x = 1\n', 'coverage.xml': xml})
    assert report.testing.coverage is None
