import type { LocalAnalysisResult } from '../../contracts/analysis';

import { MermaidPreview } from '../architecture/MermaidPreview';

import { sourceHref, query, type LocalRepository } from './api';

import { useLocale } from './locale';

type Review = NonNullable<LocalAnalysisResult['review']>;

type Explanation = Review['purpose'];

const advice: Record<string, [string, string, string, string]> = {

 hardcoded_secret:['Possible embedded credential','Olası gömülü kimlik bilgisi','Check whether this is a real credential. If so, rotate it and load it from a managed secret source.','Gerçek kimlik bilgisi olup olmadığını kontrol et. Gerçekse yenile ve güvenli bir sır kaynağından oku.'],

 dynamic_sql:['Dynamic SQL construction','Dinamik SQL oluşturma','Trace where the input comes from and use bound query parameters.','Girdinin nereden geldiğini izle ve sorguda bağlı parametreler kullan.'],

 jwt_validation:['Token verification risk','Token doğrulama riski','Check signature, expiry and expected issuer before trusting token claims.','Token içeriğine güvenmeden önce imza, süre ve beklenen sağlayıcıyı doğrula.'],

 sensitive_log:['Sensitive logging candidate','Hassas günlük kaydı adayı','Inspect the logged value and redact credentials or personal data.','Günlüğe yazılan değeri incele; kimlik bilgilerini ve kişisel verileri maskele.'],

 possible_missing_auth:['Authorization needs review','Yetkilendirme incelenmeli','Check route-level and global authorization together. A public annotation alone does not prove exposure.','Uç nokta ve genel yetkilendirmeyi birlikte kontrol et. Açık erişim işareti tek başına açıklık kanıtı değildir.'],

 environment_secret:['Secret handling needs review','Sırların kullanımı incelenmeli','Trace the value to ensure it cannot reach logs or responses.','Değerin günlüklere veya yanıtlara sızmadığını kontrol et.'],

 long_function:['Long function','Uzun fonksiyon','Identify independent responsibilities, add behavior tests and extract one responsibility at a time.','Bağımsız sorumlulukları belirle, davranış testleri ekle ve sorumlulukları tek tek ayır.'],

 deep_nesting:['Deeply nested control flow','İç içe kontrol akışı','Cover branch boundaries with tests, then consider guard clauses to simplify the flow.','Önce dal sınırlarını test et; ardından erken dönüşlerle akışı sadeleştir.'],

 magic_number:['Unexplained numeric constant','Açıklanmamış sayısal sabit','Give the value a domain-specific name and test its boundary behavior.','Değere anlamını anlatan bir ad ver ve sınır davranışını test et.'],

};

function ExplanationBlock({value,repo}: {value:Explanation;repo:LocalRepository}) {

 const {t} = useLocale();

 return value.claims.length ? <div className="review-explanation">{value.status==='static'&&<span className="local-badge">{t('Static evidence')}</span>}{value.claims.map((claim,i)=><div key={i}><p>{claim.text}</p><div className="review-citations">{claim.citations.map((cite,j)=><details key={j}><summary><a href={sourceHref(repo.repository_id,repo.snapshot_id,cite.path,cite.start_line)}>{cite.path}:{cite.start_line}</a></summary><pre>{cite.quote}</pre></details>)}</div></div>)}</div> : <p className="local-muted">{t('The model could not produce a source-backed explanation.')} <span className="local-badge">{t(value.status)}</span></p>;

}

export function RepositoryReview({report,repo}: {report:LocalAnalysisResult;repo:LocalRepository}) {

 const {t,language} = useLocale();

 const review=report.review!;

 const href=(path:string,line=1)=>sourceHref(repo.repository_id,repo.snapshot_id,path,line);

 return <div className="repository-review" data-analysis-id={report.analysis_id}>

  <div className="review-intro"><div><span className="local-eyebrow">{t('Project review')}</span><h2>{repo.name}</h2><p className="local-muted">{t('Report language')}: {review.language==='tr'?'Türkçe':'English'} · {new Date(review.generated_at).toLocaleString(language==='tr'?'tr-TR':'en-GB')}</p></div><a className="local-secondary" download={`${repo.name}-analysis.json`} href={`/api/local/export?${query(repo)}`}>{t('Download full analysis')}</a></div>

  {review.language!==language && <p role="status" className="review-notice">{t('Run analysis again to generate explanations in the selected language.')}</p>}

  <section><h3>{t('What this project does')}</h3><ExplanationBlock value={review.purpose} repo={repo}/>{review.readme_path&&<a href={href(review.readme_path)}>{t('Read the project README')}</a>}</section>

  <div className="review-columns"><section><h3>{t('Start reading here')}</h3><p className="local-muted">{t('Entry point candidates from declarations; runtime paths were not executed.')}</p>{review.entry_points.length?<ul>{review.entry_points.map((entry,i)=><li key={i}><a href={href(entry.path,entry.start_line)}>{entry.path}:{entry.start_line}</a></li>)}</ul>:<p>{t('No explicit entry point found.')}</p>}</section><section><h3>{t('Analysis scope')}</h3><dl className="review-scope">{[['Source files',review.scope.source_files],['Parsed files',review.scope.parsed_files],['Excluded files',review.scope.excluded_files],['Explained modules',review.scope.explained_modules]].map(([label,count])=><div key={label}><dt>{t(String(label))}</dt><dd>{count}</dd></div>)}</dl><p className="local-muted">{t('Source links verify location, not whether a model interpretation is correct.')}</p><p className="local-muted">{language==='tr'?'AI özeti en fazla üç modülü ve iki öncelikli bulguyu inceler; her açıklamada en fazla 48 kaynak satırı kullanılır. Diğer bulgular statik analizden gelir.':'AI explanations cover up to three modules and two priority findings, with at most 48 source lines per explanation. Other findings come from static analysis.'}</p></section></div>

  <section><h3>{t('What to fix first')}</h3><p className="local-muted">{language==='tr'?'Statik kuralların önem sırasıdır; çalışma zamanında doğrulanmış hata listesi değildir.':'Ordered by static rule severity; these are candidates, not runtime-confirmed defects.'} {review.priorities.length}/{review.scope.total_findings}</p>{review.priorities.length?<ol className="review-actions">{review.priorities.map(action=>{const tip=advice[action.issue_type]; const original=report.findings.find(f=>f.id===action.finding_id);return <li key={action.finding_id}><span className="local-badge">{t(action.severity)}</span><h4>{tip?tip[language==='tr'?1:0]:action.issue_type.replaceAll('_',' ')}</h4><p>{tip?tip[language==='tr'?3:2]:t('Inspect the linked code and its callers before changing it.')}</p><a href={href(action.location.path,action.location.start_line)}>{action.location.path}:{action.location.start_line}</a>{action.explanation.claims.length>0&&<><h5>{t('Local AI explanation')}</h5><ExplanationBlock value={action.explanation} repo={repo}/></>}{original&&!report.items.some(i=>i.id===original.id&&i.roles.includes('security'))&&<details><summary>{t('Original analyzer detail')}</summary><p>{original.description}</p><p>{original.suggestion}</p></details>}</li>})}</ol>:<p>{(language==='tr'?'Öncelikli düzeltme önerisi yok. Tüm kural eşleşmeleri Bulgular bölümünde; bu sonuç hatasızlık garantisi değildir.':'No prioritized changes. All rule matches remain in Findings; this is not a clean bill of health.')}</p>}</section>

  <section><h3>{t('Important modules')}</h3>{review.modules.length?<div className="review-modules">{review.modules.map(module=><article key={module.path}><h4><a href={href(module.path)}>{module.path}</a></h4><span className="local-badge">{module.language}</span>{module.explanation.status!=='not_requested'&&<ExplanationBlock value={module.explanation} repo={repo}/>}<details><summary>{t('Source declarations')} ({module.symbols.length})</summary><ul>{module.symbols.map((symbol,i)=><li key={i}><a href={href(module.path,symbol.start_line)}>{symbol.name}:{symbol.start_line}</a></li>)}</ul></details></article>)}</div>:<p>{t('No parsed modules. Check excluded files and supported languages.')}</p>}</section>

  {review.diagram&&<section><h3>{t('How the parts connect')}</h3><p className="local-muted">{language==='tr'?'Kaynakta bulunan bağlantılar; uygulamanın çalışma sırası değildir. Ayrıntılar ve kaynak bağlantıları Bağımlılıklar bölümünde.':'Source relationships, not runtime execution order. Open Dependencies for edge details and source links.'}</p><MermaidPreview source={review.diagram} kind="component" title={t('How the parts connect')}/></section>}

  <section><h3>{t('Testing')}</h3><p>{language==='tr'?`${report.testing?.test_files.length??0} test dosyası bulundu. Testler çalıştırılmadı.`:`${report.testing?.test_files.length??0} test files found. Tests were not executed.`}</p><p>{report.testing?.coverage?`${t('Coverage:')} ${report.testing.coverage.percent}%`:t('No coverage artifact supplied. Tests were not executed.')}</p></section>

  {report.errors.map((error,i)=><p role="status" key={i}>{error.code}: {error.message}</p>)}

 </div>;

}
