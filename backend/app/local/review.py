"""Source-backed local repository review; never executes imported code."""

from collections import Counter, defaultdict

from app.diagrams import render_mermaid
from app.local.search import related_locations, select_evidence

from datetime import datetime, timezone

from pathlib import PurePosixPath

import re



from app.rag.chat.service import ChatPrompt, ChatProviderAnswer, INSTRUCTIONS, _redact



VERSION = 1





def explain(provider, source, path, line, question, *, related=()):
    if provider is None:
        return {'status': 'unavailable', 'claims': []}
    hits = []
    for selected_path, selected_line in [(path, line), *list(related)[:2]]:
        if selected_path not in source.sources:
            continue
        lines = source.sources[selected_path].splitlines()
        start = max(0, selected_line - 1)
        text = _redact('\n'.join(lines[start:start + 48]))
        hits.append({'path': selected_path, 'start_line': start + 1, 'end_line': start + len(text.splitlines()), 'text': text})
    evidence = select_evidence(hits, question, source.commit_sha or source.snapshot_id, multi_file=bool(related))
    if not evidence:
        return {'status': 'no_evidence', 'claims': []}
    known = {item.id: item for item in evidence}
    try:
        output = ChatProviderAnswer.model_validate(provider.answer(ChatPrompt(INSTRUCTIONS, question, evidence)))
        claims = []
        for claim in output.claims:
            citations = []
            for cite in claim.citations:
                item = known.get(cite.evidence_id)
                if item is None or not item.start_line <= cite.start_line <= cite.end_line <= item.end_line:
                    raise ValueError('Citation outside selected source')
                original = '\n'.join(source.sources[item.path].splitlines()[cite.start_line - 1:cite.end_line])
                if not cite.quote.strip() or cite.quote not in original or cite.quote not in item.text or _redact(cite.quote) != cite.quote:
                    raise ValueError('Citation differs from supplied source')
                citations.append({'path': item.path, 'start_line': cite.start_line, 'end_line': cite.end_line, 'quote': cite.quote})
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

    application_modules = [module for module in modules if not support_file(module['path'])]
    purpose = {'status': 'no_evidence', 'claims': []}

    calls = 0

    if readmes and not should_stop():

        purpose = explain(provider, source, readmes[0], 1,

                          ('Belgede ve kodda gösterilen işlemleri iki kısa cümleyle açıkla. Modül adlarından ekleme, okuma, güncelleme veya silme özelliği çıkarma; sadece görünen işlemleri anlat.' if language == 'tr' else 'Summarize the operations demonstrated in the document and code in two short sentences. Do not infer create/read/update/delete features from module names; describe only operations shown.'),
                          related=[(m['path'], 1) for m in application_modules[:2]])

        calls += provider is not None

    for module in (application_modules or modules)[:3]:

        if should_stop():

            break

        deterministic = source_explanation(source, module['path'], language)
        if deterministic is not None:
            module['explanation'] = deterministic
            continue
        related = related_locations(graph, module['path'])[:2]
        seen = {module['path'], *(path for path, _ in related)}
        for neighbor, _ in list(related):
            for path, line in related_locations(graph, neighbor):
                if path not in seen and len(related) < 2:
                    related.append((path, line))
                    seen.add(path)
        module['explanation'] = explain(provider, source, module['path'], 1,

                                       (f"{module['path']} dosyası ne yapıyor ve ilişkili dosyalara nasıl bağlanıyor? İki kısa cümleyle açıkla. Dönüş değerlerini iş anlamı tahmin etmek yerine koddaki ifadelerle anlat." if language == 'tr' else f"What does {module['path']} do and how does it connect to the related files? Give two short sentences. Describe return values using the code expressions instead of guessing domain meanings."),
                                       related=related)

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
