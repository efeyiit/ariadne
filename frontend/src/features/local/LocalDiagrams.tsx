import { useEffect, useId, useState } from 'react';
import { MermaidPreview } from '../architecture/MermaidPreview';
import { request, type LocalRepository } from './api';
import { parseLocalDiagrams, type LocalDiagrams as DiagramData } from './diagrams';
import { useLocale } from './locale';

type View = 'component' | 'class' | 'sequence';
type Format = 'mermaid' | 'plantuml';
type Load = {status:'loading'} | {status:'error'} | {status:'ready';data:DiagramData};

export function LocalDiagrams({repo,analysisId}:{repo:LocalRepository;analysisId:string}) {
  const {t}=useLocale();
  const id=useId();
  const [view,setView]=useState<View>('component');
  const [format,setFormat]=useState<Format>('mermaid');
  const [showSource,setShowSource]=useState(false);
  const [attempt,setAttempt]=useState(0);
  const [load,setLoad]=useState<Load>({status:'loading'});
  const {repository_id,snapshot_id}=repo;
  useEffect(()=>{
    const controller=new AbortController();
    setLoad({status:'loading'});
    const params=new URLSearchParams({repository_id,snapshot_id,analysis_id:analysisId});
    request(`diagrams?${params}`,undefined,controller.signal)
      .then(value=>parseLocalDiagrams(value,repository_id,snapshot_id,analysisId))
      .then(data=>{if(!controller.signal.aborted)setLoad({status:'ready',data});})
      .catch(()=>{if(!controller.signal.aborted)setLoad({status:'error'});});
    return ()=>controller.abort();
  },[repository_id,snapshot_id,analysisId,attempt]);
  const current=load.status==='ready' && load.data.analysis_id===analysisId
    && load.data.repository_id===repository_id && load.data.snapshot_id===snapshot_id ? load.data : null;
  const source=current?.diagrams[format][`${view}_diagram`] ?? '';
  function download() {
    const url=URL.createObjectURL(new Blob([source],{type:'text/plain;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;
    link.download=`${view}-${analysisId}.${format==='mermaid'?'mmd':'puml'}`;
    link.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return <section className="local-diagrams" aria-labelledby={`${id}-title`}>
    <h3 id={`${id}-title`}>{t('Code diagrams')}</h3>
    <p className="local-muted">{t('Choose a view of the saved code. Mermaid previews stay on this computer; PlantUML is available as source.')}</p>
    {load.status==='error' ? <div role="alert"><p>{t('Diagrams are unavailable for this analysis. The graph may be missing or exceed the render limit.')}</p><button type="button" onClick={()=>setAttempt(value=>value+1)}>{t('Retry diagrams')}</button></div>
      : !current ? <p role="status">{t('Loading diagrams…')}</p> : <>
      <div className="local-diagram-controls">
        <label>{t('Diagram view')}<select aria-label={t('Diagram view')} value={view} onChange={event=>setView(event.target.value as View)}>
          <option value="component">{t('Files and dependencies')}</option><option value="class">{t('Classes')}</option><option value="sequence">{t('Calls')}</option>
        </select></label>
        <label>{t('Diagram format')}<select aria-label={t('Diagram format')} value={format} onChange={event=>setFormat(event.target.value as Format)}><option value="mermaid">Mermaid</option><option value="plantuml">PlantUML</option></select></label>
        <button type="button" onClick={download}>{t('Download diagram source')}</button>
      </div>
      {view==='sequence' && <p className="local-muted">{t('Calls are inferred from source locations. This is not a runtime trace or proof of execution order.')}</p>}
      {view==='class' && <p className="local-muted">{t('Parsed classes and evidenced inheritance are shown. Unresolved relationships remain labelled.')}</p>}
      {format==='mermaid' && <label className="local-diagram-source-toggle"><input type="checkbox" checked={showSource} onChange={event=>setShowSource(event.target.checked)}/>{t('Show diagram source')}</label>}
      {format==='mermaid' && !showSource ? <MermaidPreview source={source} kind={view} title={t('Code diagrams')}/> : <pre className="local-pre" tabIndex={0}>{source}</pre>}
    </>}
  </section>;
}
