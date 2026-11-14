import {
  BadgeCheck, Building2, CircleHelp, ClipboardList, Database, LayoutDashboard, LogOut,
  Menu, QrCode, ScanLine, ShieldCheck, SquareActivity, X,
} from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import { api, ApiError, periodNow, type Role, type Session, type Site } from './api';
import { ErrorNote, Loading, useApi } from './common';
import { Overview, Verification } from './workbench';
import { Audit, Payroll, PrintRecord } from './handoff';
import { Administration, MyBadge } from './admin';
import { Kiosk } from './kiosk';
import './styles.css';

const nav = [
  { id: 'overview', label: 'Overview', Icon: LayoutDashboard },
  { id: 'verification', label: 'Verification', Icon: ClipboardList },
  { id: 'payroll', label: 'Payroll exports', Icon: BadgeCheck },
  { id: 'audit', label: 'Audit trail', Icon: Database },
  { id: 'administration', label: 'Administration', Icon: Building2 },
  { id: 'badge', label: 'My badge', Icon: QrCode },
];
const access: Record<string, Role[]> = {
  payroll: ['timekeeper', 'auditor'],
  audit: ['admin', 'foreman', 'engineer', 'timekeeper', 'auditor'],
  administration: ['admin'],
  badge: ['employee'],
};
const roles: Record<Role, string> = {
  admin: 'Administrator', foreman: 'Site foreman', engineer: 'Project engineer',
  timekeeper: 'Timekeeper', auditor: 'Auditor', employee: 'Employee',
};

function Brand() {
  return <a className="brand" href="#overview"><span className="brand-icon"><ScanLine size={22} /></span><span>SiteGuard<span className="brand-qr"> QR</span><small>TIMEKEEPING</small></span></a>;
}

function SignIn({ session }: { session: (session: Session) => void }) {
  const [error, setError] = useState(location.hash === "#sso-failed" ? "Single sign-on failed. Check with your administrator." : "");
  const [organization, setOrganization] = useState("");
  const [busy, setBusy] = useState(false);
  const config = useApi<{ oidc: boolean }>('/auth/options');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      session(await api<Session>('/auth/login', { method: 'POST', body: Object.fromEntries(new FormData(event.currentTarget)) }));
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  return <main className="entry">
    <aside className="entry-aside"><Brand /><div className="entry-art" aria-hidden="true"><ShieldCheck size={110} strokeWidth={1} /></div>
      <div className="entry-caption"><h2>Workforce timekeeping</h2><p>Site attendance, verification and payroll handoff.</p></div>
    </aside>
    <section className="entry-panel">
      <div className="sign-in"><div className="desktop-hidden"><Brand /></div><h1>Sign in</h1><p>Use your SiteGuard organization and account.</p>
        <ErrorNote text={error} />
        <form className="form-stack" onSubmit={submit}>
          <label>Organization code<input name="organization" required autoComplete="organization" value={organization} onChange={(event) => setOrganization(event.target.value)} /></label>
          <label>Username<input name="login" required autoComplete="username" /></label>
          <label>Password<input name="password" type="password" required autoComplete="current-password" /></label>
          <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
        {config.value?.oidc && <button className="secondary" onClick={() => {
          if (!organization.trim()) { setError('Enter your organization code to continue with SSO.'); return; }
          location.assign('/api/v1/auth/oidc/start?organization=' + encodeURIComponent(organization.trim()));
        }}>Sign in with SSO</button>}
        <a className="text-link" href="#kiosk"><ScanLine size={17} /> Open the terminal kiosk</a>
      </div>
    </section>
  </main>;
}

function getPath() {
  return window.location.hash.slice(1) || 'overview';
}

function App() {
  const [path, setPath] = useState(getPath);
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState('');
  const [period, setPeriod] = useState(periodNow);
  const [site, setSite] = useState('');
  const [menu, setMenu] = useState(false);
  const sites = useApi<Site[]>(session && session.role !== 'employee' ? '/sites' : null);
  useEffect(() => {
    const sync = () => { setPath(getPath()); setMenu(false); };
    const signOut = () => setSession(null);
    window.addEventListener('hashchange', sync);
    window.addEventListener('siteguard:signout', signOut);
    api<Session>('/auth/me').then(setSession).catch((cause: ApiError) => {
      if (cause.status !== 401 && cause.status !== 0) setError(cause.message);
    }).finally(() => setChecking(false));
    return () => {
      window.removeEventListener('hashchange', sync);
      window.removeEventListener('siteguard:signout', signOut);
    };
  }, []);

  async function signOut() {
    try {
      await api('/auth/logout', { method: 'POST' });
      setSession(null);
      setError('');
      setSite('');
      location.hash = 'overview';
    } catch (cause) { setError((cause as Error).message); }
  }

  if (path === 'kiosk') return <Kiosk />;
  if (checking) return <main className="center"><Loading /></main>;
  if (!session) return <SignIn session={(user) => { setSession(user); setError(''); }} />;
  if (path.startsWith('print/')) return <PrintRecord path={path} />;
  const active = path.split('/')[0];
  const current = access[active] && !access[active].includes(session.role) ? 'overview' : active;
  const context = { period, setPeriod, site, setSite, sites: sites.value, session };
  let content;
  if (current === 'verification') content = <Verification {...context} selected={path.split('/')[1]} />;
  else if (current === 'payroll') content = <Payroll {...context} />;
  else if (current === 'administration') content = <Administration />;
  else if (current === 'audit') content = <Audit session={session} />;
  else if (current === 'badge') content = <MyBadge />;
  else content = <Overview {...context} />;

  return <div className="app-shell">
    <aside className={`sidebar ${menu ? 'shown' : ''}`}>
      <Brand />
      <div className="workspace"><span className="workspace-icon"><Building2 size={18} /></span><span>Workspace<small>{session.site_id || 'Organization access'}</small></span></div>
      <nav aria-label="Workspace">
        {nav.filter(({ id }) => !access[id] || access[id].includes(session.role)).map(({ id, label, Icon }) =>
          <a href={'#' + id} key={id} className={current === id ? 'active' : ''} aria-current={current === id ? 'page' : undefined}><Icon size={18} />{id === 'verification' && session.role === 'employee' ? 'My attendance' : label}</a>)}
        <a href="#kiosk"><ScanLine size={18} />Terminal kiosk</a>
      </nav>
      <div className="sidebar-foot"><CircleHelp size={17} /><a href="https://github.com/ariz31/payroll/blob/main/docs/engineering/OPERATIONS_GUIDE.md" target="_blank" rel="noreferrer">Operations guide</a></div>
    </aside>
    <div className="work-area">
      <header className="top"><button className="icon-button menu" onClick={() => setMenu(!menu)} aria-label={menu ? 'Close navigation' : 'Open navigation'}>{menu ? <X /> : <Menu />}</button>
        <span className="breadcrumb"><SquareActivity size={17} /> Workbench <span>/</span> {nav.find(({ id }) => id === current)?.label || 'Overview'}</span>
        <span className="profile"><span className="avatar">{session.name.slice(0, 2).toUpperCase()}</span><span className="profile-label">{session.name}<small>{roles[session.role]}</small></span>
          <button className="icon-button" aria-label="Sign out" onClick={signOut}><LogOut size={17} /></button></span>
      </header>
      <main className="page"><ErrorNote text={error} />{content}</main>
    </div>
  </div>;
}

createRoot(document.getElementById('root')!).render(<App />);
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => undefined);
