import { z } from 'zod';

const bundle = z.object({class_diagram:z.string(),sequence_diagram:z.string(),component_diagram:z.string()});
const schema = z.object({repository_id:z.string(),snapshot_id:z.string(),analysis_id:z.string(),
  diagrams:z.object({mermaid:bundle,plantuml:bundle})});
export type LocalDiagrams = z.infer<typeof schema>;

export function parseLocalDiagrams(value:unknown, repository:string, snapshot:string, analysis:string):LocalDiagrams {
  const result=schema.parse(value);
  if(result.repository_id!==repository || result.snapshot_id!==snapshot || result.analysis_id!==analysis) {
    throw new Error('Diagrams belong to a different analysis.');
  }
  return result;
}
