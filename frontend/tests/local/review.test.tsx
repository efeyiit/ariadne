import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { LocalReport } from '../../src/features/local/LocalReport';
import type { LocalAnalysisResult } from '../../src/contracts/analysis';
import type { LocalRepository } from '../../src/features/local/api';
it('shows a source-backed review and explicit AI limitations instead of role counters',()=>{
 const report={findings:[],items:[],errors:[],review:{version:1,language:'en',generated_at:'2026-09-27T12:00:00Z',ai_status:'unavailable',purpose:{status:'unavailable',claims:[]},readme_path:'README.md',diagram:null,entry_points:[{path:'main.py',start_line:2}],modules:[],priorities:[],scope:{source_files:2,parsed_files:1,excluded_files:0,explained_modules:0,model_calls:0,total_findings:0}}} as unknown as LocalAnalysisResult;
 const repo={name:'Example',repository_id:'one',snapshot_id:'local:'+'a'.repeat(64)} as LocalRepository;
 const html=renderToStaticMarkup(<LocalReport report={report} repo={repo} view="Overview"/>);
 expect(html).toContain('What this project does');expect(html).toContain('What to fix first');
 expect(html).toContain('path=main.py&amp;line=2');expect(html).toContain('could not produce');
 expect(html).not.toContain('Analysis roles');
});
