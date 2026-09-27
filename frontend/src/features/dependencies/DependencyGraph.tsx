import { useLocale } from '../local/locale';
import { useState } from 'react';
import type { AnalysisResultData, RepositoryInfo } from '../overview/api';
import { sourceHref } from '../architecture/source-links';
import '../architecture/architecture.css';

type DependencyData = NonNullable<Extract<AnalysisResultData, { schema_version: 2 }>['dependencies']>;
type DependencyNode = DependencyData['nodes'][number];

function NodeButton({ node, selected, onSelect }: { node: DependencyNode; selected: boolean; onSelect: (id: string) => void }) {
  const { t } = useLocale();
  return <button className={`dependency-node${selected ? ' is-selected' : ''}`} type="button" aria-pressed={selected}
    aria-label={`${node.name} ${t(node.kind)} source node`} onClick={() => onSelect(node.id)}>
    <span className="dependency-node-kind">{t(node.kind)}</span><strong>{node.name}</strong><code>{node.location.path}:{node.location.start_line}</code>
  </button>;
}

function SourceLink({ repository, node, localSource }: { repository?: RepositoryInfo; node: DependencyNode; localSource?: (path: string, line: number) => string }) {
  const { t } = useLocale();
  const href = localSource?.(node.location.path, node.location.start_line) ?? (repository ? sourceHref(repository, node.location.path, node.location.start_line) : null);
  return href ? <a className="architecture-source-link" href={href} target="_blank" rel="noopener noreferrer">{t('Open source')}: {node.location.path}:{node.location.start_line}</a>
    : <span className="architecture-source-link">{node.location.path}:{node.location.start_line}</span>;
}

export function DependencyGraph({ graph, repository, localSource }: { graph: DependencyData; repository?: RepositoryInfo; localSource?: (path: string, line: number) => string }) {
  const { t } = useLocale();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  if (!graph.nodes.length && !graph.edges.length) return <div className="feature-notice"><span className="notice-mark" aria-hidden="true">{t('i')}</span><div><strong>{t('No dependencies in this snapshot')}</strong><p>{t('The report returned an empty dependency graph.')}</p></div></div>;
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  const selectedNode = selectedId ? nodes.get(selectedId) ?? null : null;
  return <>
    <div className="dependency-summary"><span><strong>{graph.nodes.length}</strong>{t('source nodes')}</span><span><strong>{graph.edges.length}</strong>{t('relationships')}</span><span><strong>{graph.cycles.length}</strong>{t('cycles')}</span></div>
    <section className="dependency-selection" aria-live="polite" aria-atomic="true">
      {selectedNode ? <><span className="section-kicker">{t('SELECTED SOURCE NODE')}</span><strong>{selectedNode.name}</strong><span>{t(selectedNode.kind)} · {selectedNode.language} · {selectedNode.location.path}:{selectedNode.location.start_line}</span><SourceLink repository={repository} node={selectedNode} localSource={localSource}/></>
        : <span>{t('Select a graph node to inspect and open its source.')}</span>}
    </section>
    {graph.critical_nodes.length > 0 && <section className="dependency-critical" aria-labelledby="critical-title"><h3 id="critical-title">{t('Critical nodes')}</h3><div className="dependency-node-list">{graph.critical_nodes.map((id) => nodes.get(id)).filter((node): node is DependencyNode => Boolean(node)).map((node) => <NodeButton key={node.id} node={node} selected={selectedId === node.id} onSelect={setSelectedId}/>)}</div></section>}
    {graph.nodes.length > 0 && <section className="dependency-graph-section" aria-labelledby="nodes-title"><div className="architecture-section-heading"><h3 id="nodes-title">{t('Graph nodes')}</h3><span>{t('Open a node’s source at this commit')}</span></div>
      <div className="dependency-node-list">{graph.nodes.map((node) => <NodeButton key={node.id} node={node} selected={selectedId === node.id} onSelect={setSelectedId}/>)}</div></section>}
    <section className="dependency-edges" aria-labelledby="edges-title"><div className="architecture-section-heading"><h3 id="edges-title">{t('Relationships')}</h3><span>{t('Resolved, ambiguous, and external edges are labeled')}</span></div>
      {graph.edges.length ? <ul>{graph.edges.map((edge, index) => {
        const source = nodes.get(edge.source); const target = edge.target ? nodes.get(edge.target) : null;
        return <li className={`dependency-edge edge-${t(edge.status)}`} key={`${edge.source}:${edge.expression}:${index}`}>
          <div className="dependency-edge-route">{source ? <NodeButton node={source} selected={selectedId === source.id} onSelect={setSelectedId}/> : <span className="dependency-endpoint">Unknown source · {edge.source}</span>}
            <span className="dependency-arrow" aria-hidden="true">→</span>
            {target ? <NodeButton node={target} selected={selectedId === target.id} onSelect={setSelectedId}/> : <span className="dependency-endpoint">{t(edge.status === 'external' ? 'External target' : 'Unresolved target')}</span>}</div>
          <div className="dependency-edge-meta"><span className={`edge-status status-${t(edge.status)}`}>{t(edge.status)}</span><span>{t(edge.kind)}</span><code>{edge.expression}</code>
            {edge.candidates.length > 0 && <span>Candidates: {edge.candidates.map((id) => nodes.get(id)?.name ?? id).join(', ')}</span>}{edge.reason && <span>{edge.reason}</span>}
            <a className="architecture-source-link" href={localSource?.(edge.location.path, edge.location.start_line) ?? (repository ? sourceHref(repository, edge.location.path, edge.location.start_line) : undefined) ?? undefined} target="_blank" rel="noopener noreferrer">{edge.location.path}:{edge.location.start_line}</a></div>
        </li>;
      })}</ul> : <p className="architecture-muted">{t('No dependency relationships were returned.')}</p>}
    </section>
    {graph.cycles.length > 0 && <section className="dependency-cycles" aria-labelledby="cycles-title"><h3 id="cycles-title">{t('Circular dependencies')}</h3><ul>{graph.cycles.map((cycle, index) => <li key={`${cycle.join('|')}:${index}`}>
      {cycle.map((id, nodeIndex) => { const node = nodes.get(id); return <span key={`${id}:${nodeIndex}`}>{node ? <NodeButton node={node} selected={selectedId === node.id} onSelect={setSelectedId}/> : <code>{id}</code>}{nodeIndex < cycle.length - 1 && <span className="cycle-arrow" aria-hidden="true">↻</span>}</span>; })}
    </li>)}</ul></section>}
  </>;
}
