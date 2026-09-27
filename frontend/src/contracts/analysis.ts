import { z } from 'zod';

const strict = <T extends z.ZodRawShape>(shape: T) => z.strictObject(shape);

export const repositorySnapshotSchema = strict({
  repository_id: z.string().min(1),
  commit_sha: z.string().regex(/^[0-9a-f]{40}$/),
});

export const localSnapshotSchema = strict({
  repository_id: z.string().min(1),
  source_kind: z.literal('local'),
  commit_sha: z.null(),
  snapshot_id: z.string().regex(/^local:[0-9a-f]{64}$/),
});

export const sourceSnapshotSchema = z.union([repositorySnapshotSchema, localSnapshotSchema]);

export function snapshotRevision(snapshot: { repository_id: string; commit_sha: string | null; snapshot_id?: string }): string {
  if (snapshot.commit_sha !== null) return snapshot.commit_sha;
  if (snapshot.snapshot_id) return snapshot.snapshot_id;
  throw new Error('Snapshot has no source identity');
}

export const sourceLocationSchema = strict({
  path: z.string().min(1).refine((path) =>
    !path.startsWith('/') &&
    !path.includes('\\') &&
    !/^[A-Za-z]:/.test(path) &&
    !path.split('/').some((part) => part === '' || part === '.' || part === '..') &&
    !/[\x00-\x1f]/.test(path),
  ),
  start_line: z.number().int().positive(),
  end_line: z.number().int().positive(),
}).refine((location) => location.end_line >= location.start_line);

export const analysisFindingSchema = strict({
  id: z.string().min(1),
  source: z.enum(['static', 'ai']),
  issue_type: z.string().min(1),
  severity: z.enum(['info', 'low', 'medium', 'high', 'critical']),
  location: sourceLocationSchema,
  description: z.string().min(1),
  suggestion: z.string().nullable(),
});

export const analysisErrorSchema = strict({
  code: z.string().regex(/^[A-Z][A-Z0-9_]*$/),
  message: z.string().min(1),
  retryable: z.boolean(),
  location: sourceLocationSchema.nullable(),
});

const analysisResultV1Schema = strict({
  schema_version: z.literal(1),
  analysis_id: z.string().min(1),
  snapshot: repositorySnapshotSchema,
  status: z.enum(['pending', 'running', 'succeeded', 'failed']),
  findings: z.array(analysisFindingSchema),
  errors: z.array(analysisErrorSchema),
}).superRefine((result, context) => {
  if (result.status === 'failed' && result.errors.length === 0) {
    context.addIssue({ code: 'custom', message: 'failed analysis requires at least one error' });
  }
  if (result.status === 'succeeded' && result.errors.length > 0) {
    context.addIssue({ code: 'custom', message: 'succeeded analysis cannot contain errors' });
  }
  if (new Set(result.findings.map((item) => item.id)).size !== result.findings.length) {
    context.addIssue({ code: 'custom', message: 'finding ids must be unique within an analysis' });
  }
});

const roleName = z.enum(['architect', 'security', 'testing', 'refactoring', 'documentation']);
const roleSchema = strict({ role: roleName,
  status: z.enum(['succeeded', 'failed', 'timed_out', 'cancelled']), error_code: z.string().nullable() });
const itemSchema = strict({
  id: z.string(), kind: z.enum(['static_finding', 'architecture_support', 'architecture_contradiction',
    'testing_observation', 'refactoring_candidate', 'documentation_fact']), roles: z.array(roleName),
  origin: z.enum(['static', 'deterministic']), location: sourceLocationSchema.nullable(),
  text: z.string(), finding: analysisFindingSchema.nullable(),
});
const conflictSchema = strict({ key: z.string(), item_ids: z.array(z.string()) });
const architectureEvidence = strict({ description: z.string(), location: sourceLocationSchema });
const architectureName = z.enum(['mvc', 'layered', 'clean', 'hexagonal', 'microservices', 'modular_monolith', 'event_driven']);
const architectureSchema = strict({ hypotheses: z.array(strict({
  architecture: architectureName, assessment: z.enum(['supported', 'mixed', 'insufficient']),
  confidence: z.enum(['low', 'medium', 'high']), reasons: z.array(architectureEvidence),
  contradictions: z.array(architectureEvidence), uncertainties: z.array(z.string()),
})), summary: z.enum(['single', 'mixed', 'unknown']), primary: architectureName.nullable() });
const testingSchema = strict({
  test_files: z.array(strict({ path: z.string(), framework: z.string().nullable(), declaration_count: z.number().int() })),
  services: z.array(strict({ path: z.string(), name: z.string(), location: sourceLocationSchema,
    status: z.string(), test_paths: z.array(z.string()) })),
  coverage: strict({ artifact_path: z.string(), format: z.string(), metric: z.string(),
    covered: z.number().int(), total: z.number().int(), percent: z.number() }).nullable(),
  coverage_status: z.string(), coverage_errors: z.array(z.string()),
});
const refactoringSchema = strict({
  evidence: z.array(strict({ id: z.string(), kind: z.enum(['class', 'method', 'quality', 'architecture']),
    description: z.string(), location: sourceLocationSchema })),
  recommendations: z.array(strict({ principle: z.literal('srp'), certainty: z.literal('candidate'),
    origin: z.literal('deterministic'), location: sourceLocationSchema, subject: z.string(), rationale: z.string(),
    evidence_ids: z.array(z.string()), extractions: z.array(strict({ responsibility: z.string(),
      method_names: z.array(z.string()), action: z.string() })) })),
  architecture_context: z.array(strict({ architecture: z.string(), assessment: z.enum(['supported', 'mixed']),
    evidence_ids: z.array(z.string()) })), ai_status: z.literal('unavailable'), limitations: z.array(z.string()),
});
const documentEvidence = strict({ path: z.string(), line: z.number().int() });
const apiField = strict({ name: z.string(), type: z.string() });
const documentationSchema = strict({ snapshot: repositorySnapshotSchema, ai_status: z.literal('unavailable'),
  readme: z.string(), api_markdown: z.string(),
  facts: z.array(strict({ text: z.string(), evidence: documentEvidence })),
  routes: z.array(strict({ method: z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']), path: z.string(),
    request_fields: z.array(apiField), response_fields: z.array(apiField), evidence: documentEvidence,
    status: z.literal('draft') })), uncertainties: z.array(z.string()),
});
const dependenciesSchema = strict({
  nodes: z.array(strict({ id: z.string(), kind: z.enum(['file', 'symbol']),
    language: z.enum(['python', 'typescript', 'java', 'csharp', 'cpp']), name: z.string(),
    location: sourceLocationSchema })),
  edges: z.array(strict({ source: z.string(), target: z.string().nullable(),
    kind: z.enum(['import', 'call', 'inheritance']), status: z.enum(['resolved', 'external', 'ambiguous']),
    expression: z.string(), location: sourceLocationSchema, candidates: z.array(z.string()),
    reason: z.string().nullable() })), cycles: z.array(z.array(z.string())), critical_nodes: z.array(z.string()),
});

function makeAnalysisV2Schema<T extends typeof repositorySnapshotSchema | typeof sourceSnapshotSchema>(snapshot: T) {
return strict({
  schema_version: z.literal(2), analysis_id: z.string().min(1), snapshot,
  status: z.enum(['pending', 'running', 'succeeded', 'failed', 'partial', 'cancelled']),
  findings: z.array(analysisFindingSchema), errors: z.array(analysisErrorSchema),
  partial: z.boolean(), ai_status: z.literal('unavailable'), roles: z.array(roleSchema),
  items: z.array(itemSchema), conflicts: z.array(conflictSchema),
  architecture: architectureSchema.nullable(), testing: testingSchema.nullable(),
  refactoring: refactoringSchema.nullable(), documentation: documentationSchema.extend({ snapshot }).nullable(),
  dependencies: dependenciesSchema.nullable(),
}).superRefine((result, context) => {
  const error = (message: string) => context.addIssue({ code: 'custom', message });
  if (result.partial !== (result.status === 'partial')) error('partial flag must match status');
  if (result.status === 'failed' && result.errors.length === 0) error('failed analysis requires an error');
  if (result.status === 'succeeded' && result.errors.length) error('succeeded analysis cannot contain errors');
  if (new Set(result.findings.map((item) => item.id)).size !== result.findings.length) error('duplicate finding id');
  if (['succeeded', 'partial', 'failed', 'cancelled'].includes(result.status) &&
      (result.roles.length !== 5 || new Set(result.roles.map((role) => role.role)).size !== 5)) error('terminal report requires five roles');
  if (result.status === 'succeeded' && result.roles.some((role) => role.status !== 'succeeded')) error('succeeded analysis requires all roles');
  if (result.status === 'partial' && (!result.roles.some((role) => role.status === 'succeeded') ||
      !result.roles.some((role) => role.status === 'failed' || role.status === 'timed_out') ||
      result.errors.length === 0)) error('partial analysis requires success, failure and errors');
  const ids = new Set(result.items.map((item) => item.id));
  if (ids.size !== result.items.length || result.conflicts.some((conflict) => conflict.item_ids.some((id) => !ids.has(id))))
    error('report items and conflicts must be internally linked');
});
}

const analysisResultV2Schema = makeAnalysisV2Schema(repositorySnapshotSchema);

export const analysisResultSchema = z.union([analysisResultV1Schema, analysisResultV2Schema]);

const explanationSchema = z.object({status: z.enum(['answered','static','unavailable','rejected','no_evidence','not_requested']),
  claims: z.array(z.object({text:z.string(),citations:z.array(z.object({path:z.string(),start_line:z.number().int().positive(),end_line:z.number().int().positive(),quote:z.string()}))}))});
const reviewSchema = z.object({version:z.literal(1),language:z.enum(['en','tr']),generated_at:z.string(),ai_status:z.enum(['available','unavailable']),
  purpose:explanationSchema,readme_path:z.string().nullable(),diagram:z.string().nullable(),entry_points:z.array(z.object({path:z.string(),start_line:z.number()})),
  modules:z.array(z.object({path:z.string(),start_line:z.number(),language:z.string(),connections:z.number(),symbols:z.array(z.object({name:z.string(),start_line:z.number()})),explanation:explanationSchema})),
  priorities:z.array(z.object({finding_id:z.string(),severity:z.string(),issue_type:z.string(),location:sourceLocationSchema,explanation:explanationSchema})),
  scope:z.object({source_files:z.number(),parsed_files:z.number(),excluded_files:z.number(),explained_modules:z.number(),model_calls:z.number(),total_findings:z.number()})});
export const localAnalysisResultSchema = makeAnalysisV2Schema(sourceSnapshotSchema).safeExtend({review:reviewSchema.optional()});
export type LocalAnalysisResult = z.infer<typeof localAnalysisResultSchema>;

export type AnalysisResult = z.infer<typeof analysisResultSchema>;

export function parseAnalysisResult(input: unknown): AnalysisResult {
  return analysisResultSchema.parse(input);
}
