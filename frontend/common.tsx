import { CircleAlert, Inbox } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { api, type Site, type Status } from './api';

export function useApi<T>(path: string | null, revision = 0) {
  const [state, set] = useState<{ value?: T; error?: string; loading: boolean }>({ loading: Boolean(path) });
  useEffect(() => {
    let active = true;
    if (!path) {
      set({ loading: false });
      return;
    }
    set({ loading: true });
    api<T>(path).then((value) => { if (active) set({ value, loading: false }); })
      .catch((error: Error) => { if (active) set({ error: error.message, loading: false }); });
    return () => { active = false; };
  }, [path, revision]);
  return state;
}

export function Heading({ title, children, actions }: { title: string; children?: ReactNode; actions?: ReactNode }) {
  return <header className="page-heading"><div><h1>{title}</h1>{children && <p>{children}</p>}</div>{actions}</header>;
}

export function ErrorNote({ text }: { text?: string }) {
  return text ? <p className="notice error" role="alert"><CircleAlert size={17} />{text}</p> : null;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty"><Inbox size={27} /><p>{children}</p></div>;
}

export function Loading() {
  return <p className="loading" role="status">Loading…</p>;
}

export function Pill({ status }: { status: Status }) {
  const style = status === 'Verified' ? 'ok' : status === 'Pending Review' ? 'pending' : 'rejected';
  return <span className={`pill ${style}`}><i />{status}</span>;
}

export function PeriodSite({ period, setPeriod, site, setSite, sites }: {
  period: string; setPeriod: (value: string) => void;
  site?: string; setSite?: (value: string) => void; sites?: Site[];
}) {
  return <div className="filters">
    <label>Pay period<input type="month" min="2000-01" max="2099-12" value={period}
      onChange={(event) => { if (event.target.value) setPeriod(event.target.value); }} /></label>
    {setSite && sites && <label>Site<select value={site || ''} onChange={(event) => setSite(event.target.value)}>
      <option value="">All assigned sites</option>{sites.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select></label>}
  </div>;
}

export function saveLocal(name: string, type: string, contents: string) {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
