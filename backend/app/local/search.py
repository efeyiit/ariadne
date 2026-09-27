"""Snapshot-local lexical ranking and bounded, source-coordinate-preserving context."""

from collections import Counter
from math import log
from pathlib import PurePosixPath
import re

from app.rag.chat.service import Evidence, _redact


STOP = set('the a an is are does do what how this that in of for to and or from with return def class import self hangi nedir nasıl bu bir ve ile için ne'.split())


def tokens(text):
    words = re.findall(r'[^\W\d]\w*', text, re.UNICODE)
    result = []
    for word in words:
        parts = re.sub(r'([a-z])([A-Z])', r'\1 \2', word).replace('_', ' ').split()
        result.extend(term for term in {word.casefold(), *(p.casefold() for p in parts)} if term not in STOP)
    return result


def chunks_for(source):
    chunks = []
    for path, text in sorted(source.sources.items()):
        lines = text.splitlines()
        for start in range(0, len(lines), 42):
            selected = []
            for line in _redact('\n'.join(lines[start:start + 48])).splitlines():
                if sum(len(item) + 1 for item in selected) + len(line) > 8000:
                    break
                selected.append(line)
            excerpt = '\n'.join(selected)
            if excerpt.strip():
                chunks.append({'repository_id': source.repository_id, 'snapshot_id': source.snapshot_id,
                               'path': path, 'start_line': start + 1, 'end_line': start + len(selected), 'text': excerpt})
            if len(chunks) > 2048:
                raise ValueError('Optional AI indexing is limited to 2048 source chunks')
    return chunks


def mentioned_paths(question, paths):
    query = question.casefold().replace('\\', '/')
    return {path for path in paths if any(re.search(r'(?<![\w/])' + re.escape(name.casefold()) + r'(?![\w/])', query)
                                        for name in (path, PurePosixPath(path).name))}


def multiple_files(question, paths):
    return len(mentioned_paths(question, paths)) > 1 or bool(re.search(
        r'\b(trace|flow|across|between|pipeline|together|architecture|project|akış\w*|aras\w*|birlikte|mimari\w*|proje\w*)\b',
        question.casefold()))


def rank_chunks(chunks, dense_hits, question):
    """BM25 within this snapshot + reciprocal ranks; identifiers get exact-match boosts."""
    if not chunks:
        return []
    key = lambda chunk: (chunk['path'], chunk['start_line'])
    dense = {key(hit): rank for rank, hit in enumerate(dense_hits, 1)}
    terms = set(tokens(question))
    counts = [Counter(tokens(chunk['path'] + '\n' + chunk['text'])) for chunk in chunks]
    df = Counter(term for count in counts for term in terms if term in count)
    average = sum(sum(count.values()) for count in counts) / len(counts) or 1
    lexical = {}
    exact = set(re.findall(r'\b\w+_\w+\b|\b[a-z]+[A-Z]\w*\b', question))
    named = mentioned_paths(question, {chunk['path'] for chunk in chunks})
    boosts = {}
    for chunk, count in zip(chunks, counts, strict=True):
        length = sum(count.values())
        score = sum(log(1 + (len(chunks) - df[term] + .5) / (df[term] + .5))
                    * count[term] * 2.2 / (count[term] + 1.2 * (.25 + .75 * length / average))
                    for term in terms if count[term])
        if score:
            lexical[key(chunk)] = score
        boosts[key(chunk)] = (.2 if chunk['path'] in named else 0) + .1 * sum(
            bool(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', chunk['text'])) for term in exact)
    lexical_ranks = {identity: rank for rank, identity in enumerate(sorted(lexical, key=lambda identity: (-lexical[identity], identity)), 1)}
    scored = []
    for chunk in chunks:
        identity = key(chunk)
        score = boosts[identity] + (1 / (30 + dense[identity]) if identity in dense else 0)
        score += 1 / (30 + lexical_ranks[identity]) if identity in lexical_ranks else 0
        if score:
            scored.append((score, chunk))
    return [chunk for _, chunk in sorted(scored, key=lambda pair: (-pair[0], key(pair[1])))]


def related_locations(graph, path):
    nodes = {node['id']: node['location'] for node in graph.get('nodes', [])}
    found = []
    for edge in graph.get('edges', []):
        if edge['status'] != 'resolved' or edge.get('target') not in nodes or edge['source'] not in nodes:
            continue
        source, target = nodes[edge['source']], nodes[edge['target']]
        if source['path'] == target['path']:
            continue
        if source['path'] == path:
            found.append((0 if edge['kind'] == 'call' else 1, target['path'], target['start_line']))
        elif target['path'] == path:
            found.append((2, source['path'], edge['location']['start_line']))
    seen, result = set(), []
    for _, other, line in sorted(found):
        if other not in seen:
            seen.add(other)
            result.append((other, line))
    return result


def expand_related(hits, graph, question, *, inventory=None):
    if not hits or not multiple_files(question, {hit['path'] for hit in hits}):
        return hits
    # At most two graph hops and four files; only resolved saved relationships.
    selected, seen = [hits[0]], {hits[0]['path']}
    inventory = hits if inventory is None else inventory
    for _ in range(2):
        for seed in list(selected):
            for path, line in related_locations(graph, seed['path']):
                candidates = [hit for hit in inventory if hit['path'] == path]
                if path in seen or not candidates or len(selected) >= 4:
                    continue
                selected.append(min(candidates, key=lambda h: 0 if h['start_line'] <= line <= h['end_line'] else abs(h['start_line'] - line)))
                seen.add(path)
    return selected + [hit for hit in hits if hit['path'] not in seen]


def select_evidence(hits, question, revision, *, multi_file=None):
    paths = {hit['path'] for hit in hits}
    named = mentioned_paths(question, paths)
    multi = multiple_files(question, paths) if multi_file is None else multi_file
    selected, seen = [], set()
    budget = 6000
    terms = set(tokens(question))
    for hit in hits:
        if hit['path'] in seen or (len(named) > 1 and hit['path'] not in named):
            continue
        lines = hit['text'].splitlines()
        window = 24 if multi else 48
        anchor = max(range(len(lines)), key=lambda i: len(set(tokens(lines[i])) & terms), default=0)
        offset = max(0, min(len(lines) - window, anchor - 6))
        selected_lines = []
        allowance = min(budget, 1800 if multi else 6000)
        for line in lines[offset:offset + window]:
            if sum(len(item) + 1 for item in selected_lines) + len(line) > allowance:
                break
            selected_lines.append(line)
        text = '\n'.join(selected_lines)
        if not text.strip():
            continue
        start = hit['start_line'] + offset
        selected.append(Evidence(f'E{len(selected) + 1}', hit['path'], start,
                                 start + len(selected_lines) - 1, revision, text))
        seen.add(hit['path'])
        budget -= len(text)
        if len(selected) >= (4 if multi else 1) or budget <= 0:
            break
    return tuple(selected)
