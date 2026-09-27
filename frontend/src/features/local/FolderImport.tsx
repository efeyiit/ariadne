import { useLocale } from './locale';
import { useState } from 'react';
import { LocalIcon } from './LocalIcon';
import { request, shouldSkipPath, validateFolderBudget, type Limits } from './api';

export function FolderImport({ limits, imported, repositoryId }: { limits: Limits; imported: () => void; repositoryId?: string }) {
  const { t, language } = useLocale();
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  return <div className="local-folder"><label className="local-file-label"><span className="local-folder-action"><LocalIcon name="upload"/>{t(busy ? 'Reading folder…' : repositoryId ? 'Import updated folder' : 'Choose a source folder')}</span>
    <input type="file" multiple {...{ webkitdirectory: '' }} disabled={busy} aria-busy={busy} onChange={async event => {
      const selected = Array.from(event.target.files ?? []);
      if (!selected.length) return;
      setBusy(true);
      try {
        const relative = (file: File) => file.webkitRelativePath.split('/').slice(1).join('/') || file.name;
        const allowed = selected.filter(file => !shouldSkipPath(relative(file)));
        validateFolderBudget(allowed, limits);
        const files: {path: string; content: string}[] = [];
        for (const [index, file] of allowed.entries()) {
          setStatus(language === 'tr' ? `${allowed.length} dosyadan ${index + 1}. dosya okunuyor…` : `Reading ${index + 1} of ${allowed.length} files…`);
          files.push({ path: relative(file), content: await file.text() });
        }
        setStatus('Saving source snapshot…');
        const result = await request('import', { name: selected[0].webkitRelativePath.split('/')[0] || 'Local folder', files, repository_id: repositoryId ?? null });
        setStatus(language === 'tr' ? `Aktarıldı. ${selected.length - allowed.length} dosya atlandı; ${Object.keys(result.excluded).length} dosya da kapsam dışında kaldı.` : `Imported. ${selected.length - allowed.length} files skipped; ${Object.keys(result.excluded).length} additional exclusions.`);
        imported();
      } catch (error) { setStatus(error instanceof Error ? error.message : 'Folder import failed.'); }
      finally { setBusy(false); event.target.value = ''; }
    }}/></label><p className="local-muted">{t('Your files stay on this computer. Keys, environment files and dependency folders are skipped.')}</p><p role="status">{t(status)}</p></div>;
}
