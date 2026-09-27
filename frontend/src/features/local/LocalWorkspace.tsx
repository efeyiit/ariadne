import { LanguageSelect, useLocale } from './locale';
import { useEffect, useState } from 'react';
import type { LocalAnalysisResult } from '../../contracts/analysis';
import { FolderImport } from './FolderImport';
import { LocalReport } from './LocalReport';
import { LocalChat } from './LocalChat';
import { ThemeToggle } from '../../components/shell/ThemeToggle';
import { SourceText } from './SourceText';
import { loadReport, query, repositorySchema, request, sourceHref, startSession, type Job, type Limits, type LocalRepository } from './api';
import { LocalIcon, revealStyle } from './LocalIcon';
import './local.css';
import { Atmosphere } from './Atmosphere';

const views = ['Overview', 'Files', 'Architecture', 'Dependencies', 'Findings', 'Security', 'Testing', 'Refactoring', 'Documentation', 'AI chat'];
const message = (error: unknown) => error instanceof Error ? error.message : 'The request failed.';

function RepositoryPanel({ repo, limits, refresh }: { repo: LocalRepository; limits: Limits; refresh: () => void }) {
  const { t, language } = useLocale();
  const params = new URLSearchParams(window.location.search);
  const path = params.get('path');
  const [view, setView] = useState(path ? 'Files' : 'Overview');
  const [files, setFiles] = useState<{files: string[]; excluded: Record<string, string>} | null>(null);
  const [report, setReport] = useState<LocalAnalysisResult | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([request(`files?${query(repo)}`, undefined, controller.signal), loadReport(repo, controller.signal),
      path ? request(`source?${query(repo)}&${new URLSearchParams({ path })}`, undefined, controller.signal) : Promise.resolve(null)])
      .then(([fileList, latest, selected]) => { setFiles(fileList); setReport(latest); setSource(selected?.content ?? null); setLoading(false); })
      .catch(error => { if (!controller.signal.aborted) { setError(message(error)); setLoading(false); } });
    return () => controller.abort();
  }, [repo.repository_id, repo.snapshot_id, path]);
  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.status)) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const next = await request(`jobs/${encodeURIComponent(job.job_id)}`, undefined, controller.signal) as Job;
        if (next.analysis_id) setReport(await loadReport(repo, controller.signal));
        setJob(next);
      } catch (error) { if (!controller.signal.aborted) setError(message(error)); }
    }, 600);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [job, repo.repository_id, repo.snapshot_id]);
  const busy = starting || Boolean(job && ['queued','running'].includes(job.status));
  return <section><div className="local-heading"><div><p className="local-eyebrow">{t(repo.source_kind === 'github' ? 'PUBLIC GITHUB REPOSITORY' : 'LOCAL SOURCE SNAPSHOT')}</p><h1>{repo.name}</h1><p className="local-muted">{repo.commit_sha ? `Git commit ${repo.commit_sha.slice(0, 12)}` : `Content ${repo.snapshot_id.slice(6, 18)}`} · {t('Saved on this computer')}</p></div><button className="local-primary" disabled={busy || loading} aria-busy={busy || loading} onClick={async () => { setStarting(true); setError(''); try { setJob(await request('analyze', { repository_id: repo.repository_id, snapshot_id: repo.snapshot_id, force: true, language })); } catch (error) { setError(message(error)); } finally { setStarting(false); } }}>{t(busy ? 'Analyzing…' : report ? 'Analyze snapshot' : 'Run analysis')}</button></div>
    {job && <p role="status">{t('Analysis:')} {t(job.status)}{job.error_code ? ` · ${job.error_code}` : ''} {busy && <button onClick={async () => { try { await request(`jobs/${job.job_id}/cancel`, {}); } catch (error) { setError(message(error)); } }}>{t('Cancel')}</button>}</p>}
    {error && <p className="local-error" role="alert">{t(error)}</p>}
    <nav className="local-tabs" aria-label={t('Repository analysis views')}>{views.map(tab => <button key={t(tab)} aria-current={view === tab ? 'page' : undefined} onClick={() => setView(tab)}>{t(tab)}</button>)}</nav>
    <div className="local-report" key={view}><div className="local-section-heading"><h2>{t(view)}</h2><span className="local-section-note">{t('Saved analysis')}</span></div>{loading ? <p role="status">{t('Loading saved sources…')}</p> : view === 'Files' ? <>
      {source !== null && path && <><h3>{path}</h3><SourceText content={source} line={Math.max(1, Number(params.get('line')) || 1)}/></>}
      <ul className="local-files">{files?.files.map(file => <li key={file}><a href={sourceHref(repo.repository_id, repo.snapshot_id, file)}>{file}</a></li>)}</ul>
      {Object.keys(files?.excluded ?? {}).length > 0 && <details><summary>{t('Excluded files')} ({Object.keys(files!.excluded).length})</summary><ul>{Object.entries(files!.excluded).map(([file, reason]) => <li key={file}>{file} — {reason.replaceAll('_', ' ')}</li>)}</ul></details>}
      {repo.source_kind === 'local' && <FolderImport limits={limits} repositoryId={repo.repository_id} imported={refresh}/>}
    </> : view === 'AI chat' ? <LocalChat repo={repo}/> : report ? <LocalReport report={report} repo={repo} view={view}/> : <div className="local-empty"><h3>{t('Ready to explore this codebase')}</h3><p>{t('Run an analysis to see the structure, dependencies and findings. Each finding links back to the code.')}</p></div>}</div>
  </section>;
}

export function LocalWorkspace() {
  const { t, language } = useLocale();
  const [repos, setRepos] = useState<LocalRepository[]>([]);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [error, setError] = useState('');
  const [url, setUrl] = useState('');
  const [filter, setFilter] = useState('');
  const [sourceKind, setSourceKind] = useState<'github' | 'local'>('github');
  const [busy, setBusy] = useState(false);
  async function refresh() { setRepos(repositorySchema.array().parse(await request('repositories'))); }
  useEffect(() => { let active = true; startSession().then(async result => { if (!active) return; setLimits(result); await refresh(); }).catch(error => { if (active) setError(message(error)); }); return () => { active = false; }; }, []);
  const params = new URLSearchParams(window.location.search);
  const selected = repos.find(repo => repo.repository_id === params.get('repo'));
  const repo = selected && params.get('snapshot') ? { ...selected, snapshot_id: params.get('snapshot')!, commit_sha: params.get('snapshot')!.startsWith('github:') ? params.get('snapshot')!.slice(7) : null } : selected;
  const visibleRepos = repos.filter(item => item.name.toLocaleLowerCase().includes(filter.trim().toLocaleLowerCase()));
  return <div className="local-shell">
    <a className="skip-link" href="#main-content">{t('Skip to content')}</a>
    <aside className="local-sidebar">
      <a href="/" className="local-brand"><img src="/brand/ariadne-mark.png" alt=""/><span>{t('Ariadne')}</span></a>
      <a className="local-workspace-link" href="/" aria-current={!repo ? 'page' : undefined}><LocalIcon name="grid"/><span>{t('Workspace')}</span><span className="local-count">{repos.length}</span></a>
      <p className="local-nav-label">{t('Repositories')}</p>
      <nav aria-label={t('Saved repositories')}>{repos.map(item => <a key={item.repository_id} href={`/?${new URLSearchParams({repo: item.repository_id})}`} aria-current={item.repository_id === repo?.repository_id ? 'page' : undefined}><LocalIcon name={item.source_kind === 'github' ? 'github' : 'folder'}/><span>{item.name}<small>{t(item.source_kind === 'github' ? 'Public GitHub' : 'Local source')}</small></span></a>)}</nav>
      <div className="local-sidebar-note"><LocalIcon name="monitor"/><div>{t('On your computer')}<p><span className="status-dot"/>{t('No account required')}</p></div></div>
    </aside>
    <div className={`local-main${repo ? '' : ' local-home'}`}>
      {!repo && <Atmosphere/>}
      <header className="local-topbar"><div className="local-breadcrumb"><a href="/">{t('Workspace')}</a><span>/</span><strong>{repo?.name ?? t('Repositories')}</strong></div><div className="local-topbar-actions"><LanguageSelect/><ThemeToggle compact/></div></header>
      <main id="main-content" tabIndex={-1}>
        {error && <p className="local-error" role="alert">{t(error)}</p>}
        {!limits ? <div className="local-loading" role="status"><span className="local-spinner"/>{t('Opening your workspace…')}</div> : repo ? <RepositoryPanel key={`${repo.repository_id}:${repo.snapshot_id}`} repo={repo} limits={limits} refresh={() => { void refresh().catch(error => setError(message(error))); }}/> : <>
          <div className="local-hero">
            <div><h1>{t('Take a look around')}<br/>{t('your project.')}</h1><p>{t('Bring in a repository to explore its files, see what connects them,')}<br className="local-desktop-break"/>{t('and find the parts that could use some attention.')}</p></div>
            <p className="local-margin-note" aria-hidden="true">{t('Explore')}<br/>{t('Understand')}<br/>{t('Follow')}<br/>{t('Further')}<span/></p>
          </div>
          <div className="local-import-grid">
            <div className="local-source-switch"><h2>{t('What are you working on?')}</h2><div role="group" aria-label={t('Project source')}><button aria-pressed={sourceKind === 'github'} onClick={() => setSourceKind('github')}><LocalIcon name="github"/>{t('GitHub repository')}</button><button aria-pressed={sourceKind === 'local'} onClick={() => setSourceKind('local')}><LocalIcon name="folder"/>{t('Folder on this computer')}</button></div></div>
            <section className="local-import-section" hidden={sourceKind !== 'github'}><div className="local-import-title"><p>{t('Paste a public repository link to get started.')}</p></div>
              <form onSubmit={async event => { event.preventDefault(); setBusy(true); setError(''); try { const imported = repositorySchema.parse(await request('github', { github_url: url })); window.location.assign(`/?${new URLSearchParams({repo: imported.repository_id})}`); } catch (error) { setError(message(error)); } finally { setBusy(false); } }}>
                <label className="local-sr-only" htmlFor="github-url">{t('GitHub repository URL')}</label><div className="local-url-entry"><LocalIcon name="github"/><input id="github-url" type="url" placeholder="https://github.com/owner/repository" required value={url} disabled={busy} aria-busy={busy} onChange={event => setUrl(event.target.value)}/>
                <button className="local-primary" disabled={busy} aria-busy={busy}>{busy ? <><span className="local-spinner"/>{t('Importing…')}</> : <>{t('Open repository')}<LocalIcon name="arrow"/></>}</button></div>
              </form>
            </section>
            <section className="local-import-section" hidden={sourceKind !== 'local'}><div className="local-import-title"><p>{t('Choose a project folder, including a private repository.')}</p></div><FolderImport limits={limits} imported={() => { void refresh().catch(error => setError(message(error))); }}/></section>
          </div>
          <section className="local-library" aria-labelledby="repository-list-title">
            <div className="local-section-heading"><h2 id="repository-list-title">{t('Your repositories')}<span className="local-count">{repos.length}</span></h2><label className="local-search"><LocalIcon name="search"/><span className="local-sr-only">{t('Search repositories')}</span><input type="search" placeholder={t('Find a repository…')} value={filter} onChange={event => setFilter(event.target.value)}/></label></div>
            {visibleRepos.length ? <div className="local-repo-grid">{visibleRepos.map((item, index) => <a className="local-repo-card" style={revealStyle(index)} href={`/?${new URLSearchParams({repo:item.repository_id})}`} key={item.repository_id}>
              <span className="local-repo-symbol"><LocalIcon name={item.source_kind === 'github' ? 'github' : 'folder'}/></span><div className="local-repo-name"><h3>{item.name}</h3><span>{t(item.source_kind === 'github' ? 'Public GitHub repository' : 'Local source folder')}</span></div><code className="local-revision">{item.commit_sha ? item.commit_sha.slice(0, 7) : item.snapshot_id.slice(6, 13)}<span>{t(item.commit_sha ? 'commit' : 'snapshot')}</span></code><LocalIcon name="arrow"/>
            </a>)}</div> : <div className="local-empty"><LocalIcon name={filter ? 'search' : 'folder'}/><h3>{t(filter ? 'No matching repositories' : 'No projects yet')}</h3><p>{t(filter ? 'Try a different repository name.' : 'Import a GitHub repository or choose a source folder above.')}</p>{filter && <button className="local-secondary" onClick={() => setFilter('')}>{t('Clear search')}</button>}</div>}
          </section>
        </>}
      </main>
      <footer className="local-footer"><span>{t('Ariadne')}<span className="local-footer-divider">/</span>{t('Explore your code')}</span><span>{t('Projects are saved on this computer.')}</span></footer>
    </div>
  </div>;
}
