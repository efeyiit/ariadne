import { describe, expect, it } from 'vitest';
import { createSandboxDocument, validateMermaidSource, validateMermaidSvg } from '../../src/features/architecture/mermaid-security';

describe('Mermaid input and sandbox boundary', () => {
  it('preserves intrinsic diagram size instead of shrinking text to the frame', () => {
    const document = createSandboxDocument('<svg viewBox="-8 -8 920 1800"><text>Readable</text></svg>');
    expect(document).toContain('width:920px!important');
    expect(document).toContain('height:1800px!important');
    expect(document).not.toContain('max-height:100%');
    expect(document).toContain('overflow:auto');
  });

  it('uses safe fallback dimensions when the viewBox is missing or excessive', () => {
    for (const svg of ['<svg></svg>', '<svg viewBox="0 0 1e99 10"></svg>', '<svg viewBox="0 0 -1 10"></svg>']) {
      expect(createSandboxDocument(svg)).toContain('width:800px!important');
    }
  });

  it('accepts only the expected T18 diagram grammar entry point', () => {
    expect(validateMermaidSource('classDiagram\n class n_a["User"]', 'class')).toBeNull();
    expect(validateMermaidSource('sequenceDiagram\n participant n_a as "User"', 'sequence')).toBeNull();
    expect(validateMermaidSource('flowchart LR\n n_a["User"] --> n_b["Order"]', 'component')).toBeNull();
    expect(validateMermaidSource('classDiagram\n class n_a["literal %%{init text}"]', 'class')).toBeNull();
    expect(validateMermaidSource('classDiagram\n class n_a["User"]', 'sequence')).toContain('expected');
  });

  it('rejects config directives, interactive links, HTML, and oversized inputs', () => {
    expect(validateMermaidSource('flowchart LR\n%%{init: {"securityLevel":"loose"}}%%', 'component')).toContain('directive');
    expect(validateMermaidSource('flowchart LR\n click n_a "https://example.com"', 'component')).toMatch(/interactive/i);
    expect(validateMermaidSource('flowchart LR\n n_a["<script>alert(1)</script>"]', 'component')).toContain('HTML');
    expect(validateMermaidSource(`flowchart LR\n${'a'.repeat(500_001)}`, 'component')).toContain('limit');
  });

  it('allows inert SVG and rejects active, linked, or embedded markup before it reaches the sandbox', () => {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0 0L10 10"/></svg>';
    expect(validateMermaidSvg(svg)).toBeNull();
    expect(validateMermaidSvg(svg.replace('<path ', '<script '))).toContain('unsupported');
    expect(validateMermaidSvg(svg.replace('<path ', '<path onload="alert(1)" '))).toContain('event');
    expect(validateMermaidSvg(svg.replace('<path ', '<a href="https://example.com"><path '))).not.toBeNull();
    expect(validateMermaidSvg('<svg><foreignObject><img src=x onerror=alert(1) /></foreignObject></svg>')).toContain('unsupported');
    expect(createSandboxDocument(svg)).toContain("default-src 'none'");
  });
});
