import { expect, it } from 'vitest';
import { parseLocalDiagrams } from '../../src/features/local/diagrams';

const bundle = { class_diagram:'classDiagram', sequence_diagram:'sequenceDiagram', component_diagram:'flowchart LR' };
const data = {repository_id:'repo',snapshot_id:'snapshot',analysis_id:'analysis',diagrams:{mermaid:bundle,plantuml:bundle}};

it('accepts the selected analysis and rejects stale or foreign diagram responses',()=>{
  expect(parseLocalDiagrams(data,'repo','snapshot','analysis').diagrams.mermaid).toEqual(bundle);
  for(const field of ['repository_id','snapshot_id','analysis_id']) {
    expect(()=>parseLocalDiagrams({...data,[field]:'other'},'repo','snapshot','analysis')).toThrow('different analysis');
  }
});

it('rejects incomplete diagram bundles',()=>{
  expect(()=>parseLocalDiagrams({...data,diagrams:{mermaid:bundle}},'repo','snapshot','analysis')).toThrow();
});
