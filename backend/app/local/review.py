"""Source-backed local repository review; never executes imported code."""

from collections import Counter, defaultdict

from app.diagrams import render_mermaid

from datetime import datetime, timezone

from pathlib import PurePosixPath

import re



from app.rag.chat.service import ChatPrompt, ChatProviderAnswer, Evidence, INSTRUCTIONS, _redact



VERSION = 1





def explain(provider, source, path, line, question):

    if provider is None:

        return {'status': 'unavailable', 'claims': []}

    lines = source.sources[path].splitlines()

    start = max(0, line - 1)

    text = _redact('\n'.join(lines[start:start + 48]))[:6500]

    if not text.strip():

        return {'status': 'no_evidence', 'claims': []}

    end = start + len(text.splitlines())

    evidence = Evidence('E1', path, start + 1, end, source.commit_sha or source.snapshot_id, text)

    try:

        output = ChatProviderAnswer.model_validate(provider.answer(ChatPrompt(INSTRUCTIONS, question, (evidence,))))

        claims = []

        for claim in output.claims:

            citations = []

            for cite in claim.citations:

                if cite.evidence_id != 'E1' or not start + 1 <= cite.start_line <= cite.end_line <= end:

                    raise ValueError('Citation outside selected source')

                original = '\n'.join(lines[cite.start_line - 1:cite.end_line])

                if not cite.quote.strip() or cite.quote not in original or cite.quote not in text or _redact(cite.quote) != cite.quote:

                    raise ValueError('Citation differs from supplied source')

                citations.append({'path': path, 'start_line': cite.start_line, 'end_line': cite.end_line, 'quote': cite.quote})

            claims.append({'text': _redact(claim.text), 'citations': citations})

        return {'status': 'answered' if claims else 'no_evidence', 'claims': claims}

    except ValueError:

        return {'status': 'rejected', 'claims': []}

    except Exception:

        return {'status': 'unavailable', 'claims': []}





def build_review(source, report, *, language='en', provider=None, should_stop=lambda: False):

    if language not in ('en', 'tr'):

        raise ValueError('Unsupported report language')

    graph = report.get('dependencies') or {'nodes': [], 'edges': [], 'critical_nodes': [], 'cycles': []}

    symbols_by_path = defaultdict(list)

    for node in graph['nodes']:

        if node['kind'] == 'symbol':

            symbols_by_path[node['location']['path']].append(node)

    incoming = Counter(edge['target'] for edge in graph['edges'] if edge['status'] == 'resolved')

    modules = []

    for node in graph['nodes']:

        if node['kind'] != 'file':

            continue

        path = node['location']['path']

        symbols = symbols_by_path[path]

        modules.append({'path': path, 'start_line': 1, 'language': node['language'],

                        'symbols': [{'name': n['name'], 'start_line': n['location']['start_line']} for n in symbols[:12]],

                        'connections': incoming[node['id']], 'explanation': {'status': 'not_requested', 'claims': []}})

    def support_file(path):
        name = PurePosixPath(path).name.lower()
        parts = PurePosixPath(path).parts
        return (any(part.lower() in ('tests', 'test', '__tests__') for part in parts)
                or name.startswith('test_') or '.test.' in name or '.spec.' in name
                or name in ('noxfile.py', 'conftest.py', 'setup.py')
                or name.startswith(('vite.config.', 'vitest.config.')))
    modules.sort(key=lambda m: (support_file(m['path']), -m['connections'], m['path']))

    entries = []

    for path, text in sorted(source.sources.items()):

        for number, line in enumerate(text.splitlines(), 1):

            # Candidates are explicit declarations/guards, not inferred runtime reachability.

            if re.search(r'\b(?:def\s+main\s*\(|static\s+(?:void|int)\s+[Mm]ain\s*\(|int\s+main\s*\(|if\s+__name__\s*==)', line):

                entries.append({'path': path, 'start_line': number})

    readmes = sorted((p for p in source.sources if PurePosixPath(p).name.lower().startswith('readme')), key=lambda p: (p.count('/'), p))

    purpose = {'status': 'no_evidence', 'claims': []}

    calls = 0

    if readmes and not should_stop():

        purpose = explain(provider, source, readmes[0], 1,

                          ('Bu belgeye göre proje ne işe yarıyor ve kimin için? İki kısa cümleyle açıkla.' if language == 'tr' else 'According to this document, what is this project for and who uses it? Give two short sentences.'))

        calls += provider is not None

    application_modules = [module for module in modules if not support_file(module['path'])]
    for module in (application_modules or modules)[:3]:

        if should_stop():

            break

        deterministic = source_explanation(source, module['path'], language)
        if deterministic is not None:
            module['explanation'] = deterministic
            continue
        module['explanation'] = explain(provider, source, module['path'], 1,

                                       ('Bu kod ne yapıyor? Görünen sorumluluğunu en fazla iki kısa cümleyle açıkla.' if language == 'tr' else 'What does this code do? Explain its visible responsibility in at most two short sentences.'))

        calls += provider is not None

    severity = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, 'info': 4}

    actions = sorted(report['findings'], key=lambda f: (severity.get(f['severity'], 5), f['location']['path'], f['location']['start_line']))

    # Literal expected values in test fixtures are not actionable production debt.
    # Keep the original findings intact in the full report.
    def actionable(finding):
        path = PurePosixPath(finding['location']['path'])
        test_file = any(part.lower() in ('test', 'tests', '__tests__') for part in path.parts) or path.name.startswith('test_') or '.test.' in path.name or '.spec.' in path.name
        return not (finding['issue_type'] == 'magic_number' and test_file)
    priorities = []

    explanation_cache = {}

    for finding in [item for item in actions if actionable(item)][:12]:

        item = {'finding_id': finding['id'], 'severity': finding['severity'], 'issue_type': finding['issue_type'],

                'location': finding['location'], 'explanation': {'status': 'not_requested', 'claims': []}}

        if len(priorities) < 2 and not should_stop():

            loc = finding['location']

            start = max(1, loc['start_line'] - 3)

            cache_key = (loc['path'], start // 12)

            if cache_key not in explanation_cache:

                explanation_cache[cache_key] = explain(provider, source, loc['path'], start,

                    ('Bu kodun davranışını tek kısa cümleyle açıkla. Kanıtlanmayan bir hata veya güvenlik açığı varsayma.' if language == 'tr' else 'Explain the visible code behavior in one short sentence. Do not assume an unproven bug or exploit.'))

                calls += provider is not None

            item['explanation'] = explanation_cache[cache_key]

        priorities.append(item)

    explanations = [purpose] + [m['explanation'] for m in modules] + [a['explanation'] for a in priorities]

    answered = sum(e['status'] == 'answered' for e in explanations)

    try:

        diagram = render_mermaid(graph, 'component') if graph['nodes'] else None

    except ValueError:

        diagram = None

    return {'diagram': diagram, 'version': VERSION, 'language': language, 'generated_at': datetime.now(timezone.utc).isoformat(),

            'ai_status': 'available' if answered else 'unavailable', 'purpose': purpose,

            'readme_path': readmes[0] if readmes else None, 'entry_points': entries[:20],

            'modules': modules, 'priorities': priorities,

            'scope': {'source_files': len(source.sources), 'parsed_files': len(modules),

                      'excluded_files': len(source.excluded), 'explained_modules': sum(m['explanation']['status'] in ('answered', 'static') for m in modules),

                      'model_calls': calls, 'total_findings': len(actions)}}


def source_explanation(source, path, language):
    """Explain only a narrow, proven AST shape; do not evaluate any expression."""
    import ast
    if not path.endswith('.py'):
        return None
    try:
        tree = ast.parse(source.sources[path])
    except (SyntaxError, ValueError):
        return None
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        return None
    function = tree.body[0]
    if function.decorator_list or any(arg.arg == 'print' for arg in function.args.args):
        return None
    body = function.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1:
        return None
    statement = body[0]
    expression_nodes = (ast.Name, ast.Load, ast.Constant, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)
    if isinstance(statement, ast.Return) and statement.value is not None and all(isinstance(n, expression_nodes) for n in ast.walk(statement.value)):
        expression = ast.unparse(statement.value)
        text = (f'`{function.name}` fonksiyonu `{expression}` ifadesinin sonucunu döndürür.' if language == 'tr'
                else f'`{function.name}` returns the result of `{expression}`.')
    elif (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
          and isinstance(statement.value.func, ast.Name) and statement.value.func.id == 'print'
          and len(statement.value.args) == 1 and not statement.value.keywords
          and isinstance(statement.value.args[0], ast.Constant)):
        literal = repr(statement.value.args[0].value)
        text = (f'`{function.name}` fonksiyonu `{literal}` değerini yazdırır.' if language == 'tr'
                else f'`{function.name}` prints `{literal}`.')
    else:
        return None
    quote = '\n'.join(source.sources[path].splitlines()[statement.lineno-1:statement.end_lineno])
    if _redact(quote) != quote or _redact(text) != text:
        return None
    return {'status':'static','claims':[{'text':text,'citations':[{'path':path,'start_line':statement.lineno,'end_line':statement.end_lineno,'quote':quote}]}]}
