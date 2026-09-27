"""Run the synthetic multi-file citation probes against a running local app.

Creates a labelled synthetic repository in that app. This checks status, source
coverage and exact quotes; read the answers to assess semantic correctness.
"""

import argparse
import http.cookiejar
import json
from pathlib import Path
import time
from urllib.request import Request, build_opener, HTTPCookieProcessor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repository-id', help='Reuse an existing synthetic fixture repository')
    args = parser.parse_args()
    fixture = json.loads((Path(__file__).parent / 'fixtures/multifile_retrieval.json').read_text(encoding='utf-8'))
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    csrf = ''

    def call(path, body=None):
        request = Request('http://127.0.0.1:8080/api/local/' + path,
                          data=json.dumps(body).encode('utf-8') if body is not None else None,
                          headers={'Content-Type': 'application/json', 'X-CSRF-Token': csrf})
        with opener.open(request, timeout=300) as response:
            return json.load(response)

    csrf = call('session')['csrf_token']
    if call('ai')['status'] != 'ready':
        raise SystemExit('Start the local application with its model and wait until AI is ready.')
    body = {'name': 'Multi-file retrieval acceptance', 'files': fixture['files']}
    if args.repository_id:
        body['repository_id'] = args.repository_id
    source = call('import', body)
    originals = {item['path']: item['content'].splitlines() for item in fixture['files']}
    results = []
    for probe in fixture['queries']:
        start = time.monotonic()
        result = call('chat', {key: source[key] for key in ('repository_id', 'snapshot_id')}
                      | {'question': probe['question']})
        citations = [cite for claim in result['claims'] for cite in claim['citations']]
        cited = {cite['path'] for cite in citations}
        required = set(probe['required_paths'])
        exact = all(cite['path'] in originals and cite['quote'].strip()
                    and 1 <= cite['start_line'] <= cite['end_line'] <= len(originals[cite['path']])
                    and cite['quote'] in '\n'.join(originals[cite['path']][cite['start_line'] - 1:cite['end_line']])
                    and cite['snapshot_id'] == source['snapshot_id'] for cite in citations)
        passed = result['status'] == probe['expected_status'] and required <= cited and exact
        results.append({'id': probe['id'], 'passed': passed, 'required_paths': sorted(required),
                        'cited_paths': sorted(cited), 'seconds': round(time.monotonic() - start, 2), 'response': result})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'repository_id': source['repository_id'], 'results': results},
                                         ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({key: results[-1][key] for key in ('id', 'passed', 'cited_paths', 'seconds')}), flush=True)
    raise SystemExit(0 if all(item['passed'] for item in results) else 1)


if __name__ == '__main__':
    main()
