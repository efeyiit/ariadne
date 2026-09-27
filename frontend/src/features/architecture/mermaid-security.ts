export type MermaidDiagramKind = 'class' | 'sequence' | 'component';

const maxDiagramCharacters = 500_000;
const expectedStart: Record<MermaidDiagramKind, RegExp> = {
  class: /^classDiagram(?:\s|$)/,
  sequence: /^sequenceDiagram(?:\s|$)/,
  component: /^flowchart\s+LR(?:\s|$)/,
};
const allowedSvgElements = new Set([
  'svg', 'g', 'defs', 'marker', 'symbol', 'use', 'path', 'rect', 'line', 'circle', 'ellipse', 'polygon', 'polyline',
  'text', 'tspan', 'title', 'desc', 'style', 'clippath', 'mask', 'pattern', 'lineargradient',
  'radialgradient', 'stop', 'filter', 'fegaussianblur', 'feoffset', 'fecomposite', 'feflood',
  'femerge', 'femergenode', 'feblend', 'fedropshadow',
]);

export function validateMermaidSource(source: string, kind: MermaidDiagramKind): string | null {
  const normalized = source.trim();
  if (normalized.length > maxDiagramCharacters) return 'Diagram source exceeds the local render size limit.';
  if (!expectedStart[kind].test(normalized)) return `Diagram source does not match the expected ${kind} diagram.`;
  if (/^\s*%%\s*(?:\{|init\b|initialize\b)|^\s*%%/im.test(normalized)) return 'Mermaid directives and comments are disabled for repository diagrams.';
  if (/^\s*(?:click|href|callback)\b/im.test(normalized)) return 'Interactive Mermaid links are disabled.';
  if (/<\s*\/?\s*(?:script|iframe|foreignobject|html|svg|img)\b/i.test(normalized)) return 'HTML tags are not allowed in diagram labels.';
  return null;
}

export function validateMermaidSvg(svg: string): string | null {
  const normalized = svg.trim();
  if (!/^<svg\b[\s\S]*<\/svg>$/.test(normalized)) return 'Mermaid returned invalid SVG markup.';
  const elements = [...normalized.matchAll(/<\/?([A-Za-z][\w:-]*)\b[^>]*>/g)];
  if (!elements.length || elements[0][1].toLowerCase() !== 'svg') return 'Mermaid returned invalid SVG markup.';
  if (elements.some((match) => !allowedSvgElements.has(match[1].toLowerCase()))) return 'Mermaid returned an unsupported SVG element.';
  if (/\son[a-z0-9:_-]+\s*=/i.test(normalized)) return 'Mermaid SVG event handlers are not allowed.';
  const refs = [...normalized.matchAll(/\s(?:href|xlink:href|src)\s*=\s*(["'])(.*?)\1/gi)].map((match) => match[2]);
  if (refs.some((ref) => !/^#[\w:.-]+$/.test(ref))) return 'Mermaid SVG links and external resources are not allowed.';
  if (/@import|expression\s*\(|javascript\s*:|url\(\s*['"]?(?!#[\w:.-]+)['"]?\s*\)/i.test(normalized))
    return 'Mermaid SVG contains an external or executable style reference.';
  return null;
}

export function createSandboxDocument(svg: string, dark = false): string {
  const issue = validateMermaidSvg(svg);
  if (issue) throw new Error(issue);
  const background = dark ? '#2C2C2C' : '#F3F4F4';
  const rootTag = svg.trim().match(/^<svg\b[^>]*>/)?.[0] ?? '';
  const viewBox = rootTag.match(/\bviewBox\s*=\s*["']([^"']+)["']/i)?.[1].trim().split(/[\s,]+/).map(Number);
  const validSize = viewBox?.length === 4 && viewBox.every(Number.isFinite)
    && viewBox[2] > 0 && viewBox[3] > 0 && viewBox[2] <= 100_000 && viewBox[3] <= 100_000;
  const width = validSize ? viewBox[2] : 800;
  const height = validSize ? viewBox[3] : 600;
  // Keep labels at the renderer's intended size. Scrolling stays inside the
  // script-free sandbox rather than shrinking a tall graph into illegibility.
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:;"><style>html,body{box-sizing:border-box;margin:0;background:${background}}html{width:100%;height:100%;overflow:auto}body{min-height:100%;padding:8px}body>svg{display:block;width:${width}px!important;height:${height}px!important;max-width:none!important;max-height:none!important;}</style></head><body>${svg}</body></html>`;
}
