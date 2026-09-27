import { useLocale } from '../local/locale';
import { useEffect, useId, useState } from 'react';
import { createSandboxDocument, validateMermaidSource, validateMermaidSvg, type MermaidDiagramKind } from './mermaid-security';

type PreviewState = { status: 'loading' } | { status: 'ready'; document: string } | { status: 'error'; message: string };

export function MermaidPreview({ source, kind, title }: { source: string; kind: MermaidDiagramKind; title: string }) {
  const { t } = useLocale();
  const reactId = useId();
  const [theme, setTheme] = useState<'light' | 'dark'>(() => document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
  const [preview, setPreview] = useState<PreviewState>({ status: 'loading' });

  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let active = true;
    setPreview({ status: 'loading' });
    const sourceIssue = validateMermaidSource(source, kind);
    if (sourceIssue) {
      setPreview({ status: 'error', message: sourceIssue });
      return () => { active = false; };
    }

    async function render() {
      try {
        const { default: mermaid } = await import('mermaid');
        const dark = theme === 'dark';
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          secure: ['securityLevel', 'startOnLoad', 'maxTextSize', 'maxEdges'],
          suppressErrorRendering: true,
          maxTextSize: 500_000,
          maxEdges: 2_000,
          htmlLabels: false,
          theme: 'base',
          themeVariables: {
            darkMode: dark,
            background: dark ? '#2C2C2C' : '#F3F4F4',
            primaryColor: dark ? '#612D53' : '#f3e9ed',
            primaryTextColor: dark ? '#F3F4F4' : '#2C2C2C',
            primaryBorderColor: '#853953',
            lineColor: '#853953',
            secondaryColor: dark ? '#40363e' : '#fff',
            secondaryTextColor: dark ? '#F3F4F4' : '#2C2C2C',
            tertiaryColor: dark ? '#383239' : '#F3F4F4',
            tertiaryTextColor: dark ? '#F3F4F4' : '#2C2C2C',
            mainBkg: dark ? '#383239' : '#fff',
            textColor: dark ? '#F3F4F4' : '#2C2C2C',
          },
        });
        const safeId = `ariadne-${reactId.replace(/[^A-Za-z0-9_-]/g, '')}-${kind}`;
        const result = await mermaid.render(safeId, source);
        const svgIssue = validateMermaidSvg(result.svg);
        if (svgIssue) throw new Error(svgIssue);
        const sandboxDocument = createSandboxDocument(result.svg, dark);
        if (active) setPreview({ status: 'ready', document: sandboxDocument });
      } catch {
        if (active) setPreview({ status: 'error', message: 'Mermaid could not safely render this diagram. The source remains available.' });
      }
    }
    void render();
    return () => { active = false; };
  }, [source, kind, theme, reactId]);

  if (preview.status === 'loading') return <div className="diagram-preview-loading" role="status" aria-busy="true">{t('Rendering Mermaid preview locally…')}</div>;
  if (preview.status === 'error') return <div className="diagram-preview-error" role="status">{t(preview.message)}</div>;
  return <iframe className={`mermaid-sandbox mermaid-sandbox-${kind}`} title={title} sandbox="" referrerPolicy="no-referrer" srcDoc={preview.document}/>;
}
