import { useLocale } from './locale';
import { useEffect, useState } from 'react';
import { request, sourceHref, type LocalRepository } from './api';

type Answer = {status: string; answer: string; snapshot_id: string; claims: {text: string; citations: {path: string; start_line: number; quote: string}[]}[]};
export function LocalChat({ repo }: {repo: LocalRepository}) {
  const { t } = useLocale();
  const [ready, setReady] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function check() { try { setReady((await request('ai')).status === 'ready'); } catch { setReady(false); } }
  useEffect(() => { void check(); }, []);
  return <section className="local-chat"><h3>{t('Ask about the code')}</h3><p className="local-muted">{t('Ask about a function or file. The local model answers from matching code and links to the source. It may miss context from other parts of the project.')}</p>{!ready && <p role="status">{t('Local AI is not connected or is still loading. Static analysis works independently.')}<button onClick={() => { void check(); }}>{t('Check again')}</button></p>}<form onSubmit={async event => { event.preventDefault(); setBusy(true); setError(''); try { const result = await request('chat', {repository_id:repo.repository_id,snapshot_id:repo.snapshot_id,question}) as Answer; if(result.snapshot_id !== repo.snapshot_id) throw new Error('Answer belongs to another snapshot.'); setAnswer(result); } catch(error) { setError(error instanceof Error ? error.message : 'AI request failed.'); } finally {setBusy(false);} }}><label htmlFor="local-question">{t('Your question')}</label><textarea id="local-question" required maxLength={1000} value={question} onChange={event=>setQuestion(event.target.value)} disabled={!ready || busy} aria-busy={busy}/><button className="local-primary" disabled={!ready || busy} aria-busy={busy}>{t(busy ? 'Checking source evidence…' : 'Ask local AI')}</button></form>{error && <p role="alert">{t(error)}</p>}{answer && <div className="local-answer" role="status"><p className="local-badge">{t(answer.status)}</p>{answer.claims.length ? answer.claims.map((claim,i)=><article className="local-card" key={i}><p>{claim.text}</p>{claim.citations.map((cite,j)=><blockquote key={j}><p>{cite.quote}</p><a href={sourceHref(repo.repository_id,repo.snapshot_id,cite.path,cite.start_line)}>{cite.path}:{cite.start_line}</a></blockquote>)}</article>) : <p>{t(answer.answer)}</p>}</div>}</section>;
}
