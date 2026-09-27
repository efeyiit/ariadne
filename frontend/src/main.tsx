import { createRoot } from 'react-dom/client';
import { App } from './app/App';
import './styles.css';
import { LocaleProvider } from './features/local/locale';

const root = document.getElementById('root');
if (!root) throw new Error('Missing root element');

const application = createRoot(root);
application.render(<p role="status" style={{ padding: 32 }}>Opening Ariadne…</p>);
fetch('/api/runtime', { credentials: 'same-origin' }).then(async response => {
  const runtime = response.ok && response.headers.get('content-type')?.includes('application/json') ? await response.json() : null;
  if (runtime?.mode === 'local') {
    const { LocalWorkspace } = await import('./features/local/LocalWorkspace');
    application.render(<LocaleProvider><LocalWorkspace/></LocaleProvider>);
  } else application.render(<App/>);
}).catch(() => application.render(<p role="alert" style={{ padding: 32 }}>Ariadne could not be reached. Restart the local application and reload this page.</p>));
