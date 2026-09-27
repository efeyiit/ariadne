import { describe, it, expect } from 'vitest';
import { translate, initialLanguage } from '../../src/features/local/locale';
describe('language preference', () => {
  it('defaults to English even on a Turkish computer', () => {
    expect(initialLanguage(null)).toBe('en');
    expect(initialLanguage('invalid')).toBe('en');
    expect(initialLanguage('tr')).toBe('tr');
  });
  it('translates UI text without altering unknown source text', () => {
    expect(translate('tr', 'Workspace')).toBe('Çalışma alanı');
    expect(translate('en', 'Workspace')).toBe('Workspace');
    expect(translate('tr', 'def main():')).toBe('def main():');
  });
});
