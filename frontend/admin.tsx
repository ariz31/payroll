import { KeyRound, Printer, QrCode } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { api, type Role, type ShiftType, type Site } from './api';
import { Empty, ErrorNote, Heading, Loading, saveLocal, useApi } from './common';

interface Employee { id: string; name: string; department: string; cost_code: string; crew: string; shift_type: ShiftType; site_ids: string[]; active: boolean }
interface Terminal { id: string; code: string; name: string; site_id: string; latitude: number; longitude: number; active: boolean; generation: number; credential?: string }
interface StaffRow { login: string; name: string; role: Role; site_id: string | null; scope_code: string | null; employee_id: string | null; active: boolean }
interface Integration { id: string; name: string; site_id: string | null; revoked_at: string | null }
interface Badge { id: string; employee_id: string; mode: 'STC' | 'DYN'; revoked_at: string | null }
interface BadgeCode { svg: string; employee_id: string; mode: 'STC' | 'DYN'; refresh_after_ms: number | null }
interface Policy { day_start: string; day_end: string; night_start: string; night_end: string; break_mins: number; regular_hours: string;
  late_grace_minutes: number; debounce_seconds: number; high_ot_hours: string; missing_out_grace_minutes: number;
  qr_mode: string; qr_step_seconds: number; qr_drift_windows: number; offline_hours: number; auto_verify_ok_scans: boolean }

const roles: { id: Role; label: string }[] = [
  { id: 'admin', label: 'Administrator' }, { id: 'foreman', label: 'Site foreman' }, { id: 'engineer', label: 'Project engineer' },
  { id: 'timekeeper', label: 'Timekeeper' }, { id: 'auditor', label: 'Auditor' }, { id: 'employee', label: 'Employee' },
];
const tabs = [['sites', 'Sites'], ['employees', 'Employees'], ['terminals', 'Terminals'], ['badges', 'Badges'], ['users', 'Accounts'], ['config', 'Policy'], ['integrations', 'Payroll API']];
const string = (data: FormData, key: string) => String(data.get(key) || '').trim();
const number = (data: FormData, key: string) => Number(data.get(key));
const active = (data: FormData) => data.get('active') === 'on';

function changedSelect(onChange: (value: string) => void, items: { id: string; label: string }[], selection?: string, label = 'Select an existing record') {
  return <label>{label}<select value={selection || ''} onChange={(event) => onChange(event.target.value)}>
    <option value="">Create new</option>{items.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>;
}

function SiteOptions({ sites }: { sites: Site[] }) {
  return <>{sites.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.id}</option>)}</>;
}

function SiteForm({ rows, submit }: { rows: Site[]; submit: Submit }) {
  const [selection, set] = useState('');
  const row = rows.find((item) => item.id === selection);
  const [images, setImages] = useState(false);
  return <>
    {changedSelect((value) => { set(value); setImages(rows.find((item) => item.id === value)?.evidence_mode !== 'off' && Boolean(value)); },
      rows.map((item) => ({ id: item.id, label: item.name })), selection)}
    <form key={selection} className="form-stack" onSubmit={(event) => submit(event, (data) => ({
      path: '/sites/' + (row?.id || string(data, 'id')), body: {
        name: string(data, 'name'), timezone: string(data, 'timezone'), latitude: number(data, 'latitude'),
        longitude: number(data, 'longitude'), radius_m: number(data, 'radius_m'), active: active(data),
        evidence_mode: string(data, 'evidence_mode'), evidence_notice: string(data, 'evidence_notice'),
        evidence_days: Number(data.get('evidence_days') || 30),
      },
    }))}>
      <div className="form-grid">
        <label>Site code<input name="id" required defaultValue={row?.id} readOnly={!!row} /></label>
        <label>Name<input name="name" required defaultValue={row?.name} /></label>
        <label>IANA timezone<input name="timezone" required defaultValue={row?.timezone || 'Asia/Manila'} /></label>
        <label>Geofence radius (metres)<input name="radius_m" type="number" min={10} max={50000} defaultValue={row?.radius_m || 100} required /></label>
        <label>Latitude<input name="latitude" type="number" min={-90} max={90} step="any" defaultValue={row?.latitude} required /></label>
        <label>Longitude<input name="longitude" type="number" min={-180} max={180} step="any" defaultValue={row?.longitude} required /></label>
        <label>Camera evidence<select name="evidence_mode" defaultValue={row?.evidence_mode || 'off'} onChange={(event) => setImages(event.target.value !== 'off')}>
          <option value="off">Off</option><option value="optional">Optional</option><option value="required">Required</option>
        </select></label>
        {images && <label>Image retention (days)<input name="evidence_days" type="number" min={1} max={90} defaultValue={row?.evidence_days || 30} required /></label>}
      </div>
      {images && <label>Worker-facing privacy notice<textarea name="evidence_notice" defaultValue={row?.evidence_notice} required maxLength={600} /></label>}
      <label className="check"><input type="checkbox" name="active" defaultChecked={row?.active ?? true} />Active site</label>
      <button className="primary">Save site</button>
    </form>
  </>;
}

type Submit = (event: FormEvent<HTMLFormElement>, build: (data: FormData) => { path: string; body: object }) => void;

function EmployeeForm({ rows, sites, submit, onImage }: { rows: Employee[]; sites: Site[]; submit: Submit; onImage: (id: string, file: File) => Promise<void> }) {
  const [selection, set] = useState('');
  const row = rows.find((item) => item.id === selection);
  return <>
    {changedSelect(set, rows.map((item) => ({ id: item.id, label: `${item.name} · ${item.id}` })), selection)}
    <form key={selection} className="form-stack" onSubmit={(event) => submit(event, (data) => ({
      path: '/employees/' + (row?.id || string(data, 'id')), body: {
        name: string(data, 'name'), department: string(data, 'department'), cost_code: string(data, 'cost_code'),
        crew: string(data, 'crew'), shift_type: string(data, 'shift_type'), site_ids: data.getAll('site_ids'), active: active(data),
      },
    }))}>
      <div className="form-grid">
        <label>Employee ID<input name="id" required defaultValue={row?.id} readOnly={!!row} /></label>
        <label>Full name<input name="name" defaultValue={row?.name} required /></label>
        <label>Department<input name="department" defaultValue={row?.department} required /></label>
        <label>Project / cost code<input name="cost_code" defaultValue={row?.cost_code} required /></label>
        <label>Crew<input name="crew" defaultValue={row?.crew} required /></label>
        <label>Assigned shift<select name="shift_type" defaultValue={row?.shift_type}><option>Day Shift</option><option>Night Shift</option></select></label>
      </div>
      <fieldset><legend>Assigned sites</legend><div className="check-list">{sites.map((item) => <label className="check" key={item.id}>
        <input type="checkbox" name="site_ids" value={item.id} defaultChecked={row?.site_ids.includes(item.id)} />{item.name}
      </label>)}</div></fieldset>
      <label className="check"><input name="active" type="checkbox" defaultChecked={row?.active ?? true} />Active employee</label>
      <button className="primary">Save employee</button>
    </form>
    {row && sites.some((site) => row.site_ids.includes(site.id) && site.evidence_mode !== 'off') &&
      <form className="form-stack separated" onSubmit={(event) => {
        event.preventDefault();
        const file = new FormData(event.currentTarget).get('image');
        if (file instanceof File && file.size) void onImage(row.id, file);
      }}><label>Registered badge image (JPEG)<input name="image" type="file" accept="image/jpeg" required /></label>
        <button className="secondary">Save badge image</button></form>}
  </>;
}

function TerminalForm({ rows, sites, submit, rotate }: { rows: Terminal[]; sites: Site[]; submit: Submit; rotate: (code: string) => void }) {
  const [selection, set] = useState('');
  const row = rows.find((item) => item.code === selection);
  return <>
    {changedSelect(set, rows.map((item) => ({ id: item.code, label: `${item.name} · ${item.code}` })), selection)}
    <form key={selection} className="form-stack" onSubmit={(event) => submit(event, (data) => ({
      path: '/terminals/' + (row?.code || string(data, 'code')), body: {
        name: string(data, 'name'), site_id: row?.site_id || string(data, 'site_id'),
        latitude: number(data, 'latitude'), longitude: number(data, 'longitude'), active: active(data),
      },
    }))}>
      <div className="form-grid">
        <label>Terminal code<input name="code" required defaultValue={row?.code} readOnly={!!row} /></label>
        <label>Name<input name="name" defaultValue={row?.name} required /></label>
        <label>Site<select name="site_id" defaultValue={row?.site_id} disabled={!!row} required><option value="">Select site</option><SiteOptions sites={sites} /></select></label>
        <label>Enrolled latitude<input name="latitude" type="number" min={-90} max={90} step="any" defaultValue={row?.latitude} required /></label>
        <label>Enrolled longitude<input name="longitude" type="number" min={-180} max={180} step="any" defaultValue={row?.longitude} required /></label>
      </div>
      <label className="check"><input type="checkbox" name="active" defaultChecked={row?.active ?? true} />Active terminal</label>
      <div className="actions"><button className="primary">Save terminal</button>
        {row && <button className="secondary" type="button" onClick={() => {
          if (window.confirm('Rotate this terminal credential? Sync its outbox first.')) void rotate(row.code);
        }}><KeyRound size={17} />Rotate credential</button>}</div>
    </form>
  </>;
}

function UserForm({ rows, sites, submit }: { rows: StaffRow[]; sites: Site[]; submit: Submit }) {
  const [selection, set] = useState('');
  const row = rows.find((item) => item.login === selection);
  const [role, setRole] = useState<Role>('foreman');
  return <>
    {changedSelect((value) => { set(value); setRole(rows.find((item) => item.login === value)?.role || 'foreman'); },
      rows.map((item) => ({ id: item.login, label: `${item.name} · ${item.login}` })), selection)}
    <form key={selection} className="form-stack" onSubmit={(event) => submit(event, (data) => ({
      path: '/users/' + (row?.login || string(data, 'login')), body: {
        name: string(data, 'name'), role, site_id: string(data, 'site_id') || null,
        scope_code: string(data, 'scope_code') || null, employee_id: string(data, 'employee_id') || null,
        active: active(data), password: String(data.get('password') || '') || null,
      },
    }))}>
      <div className="form-grid">
        <label>Username<input name="login" defaultValue={row?.login} required readOnly={!!row} /></label>
        <label>Name<input name="name" defaultValue={row?.name} required /></label>
        <label>Role<select value={role} onChange={(event) => setRole(event.target.value as Role)}>
          {roles.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <label>Site scope<select name="site_id" defaultValue={row?.site_id || ''} required={role === 'engineer' || role === 'foreman'}>
          <option value="">Organization-wide</option><SiteOptions sites={sites} /></select></label>
        {role === 'employee' && <label>Employee ID<input name="employee_id" defaultValue={row?.employee_id || ''} required /></label>}
        {['foreman', 'engineer'].includes(role) && <label>{role === 'foreman' ? 'Crew' : 'Cost code'} scope (optional)<input name="scope_code" defaultValue={row?.scope_code || ''} /></label>}
        <label>Password {row ? '(replace if needed)' : '(leave blank for SSO)'}<input name="password" type="password" minLength={12} maxLength={256} autoComplete="new-password" /></label>
      </div>
      <label className="check"><input type="checkbox" name="active" defaultChecked={row?.active ?? true} />Active account</label>
      <button className="primary">Save account</button>
    </form>
  </>;
}

const numbers = [
  ['break_mins', 'Unpaid break (minutes)', 0, 480, 1], ['regular_hours', 'Regular hours cap', 0.01, 24, 0.01],
  ['late_grace_minutes', 'Late grace (minutes)', 0, 120, 1], ['debounce_seconds', 'Debounce (seconds)', 1, 1800, 1],
  ['high_ot_hours', 'High overtime (hours)', 0, 24, 0.01], ['missing_out_grace_minutes', 'Clock-out closing grace (minutes)', 0, 360, 1],
  ['qr_step_seconds', 'Dynamic QR step (seconds)', 15, 120, 1], ['qr_drift_windows', 'Accepted step drift', 0, 2, 1],
  ['offline_hours', 'Offline lease (hours)', 1, 48, 1],
] as const;
const times = [['day_start', 'Day shift start'], ['day_end', 'Day shift end'], ['night_start', 'Night shift start'], ['night_end', 'Night shift end']] as const;

function PolicyForm({ data, submit }: { data: { version: number; settings: Policy }; submit: Submit }) {
  const { settings } = data;
  return <form className="form-stack" onSubmit={(event) => submit(event, (form) => ({
    path: '/config', body: {
      ...Object.fromEntries(times.map(([key]) => [key, string(form, key)])),
      ...Object.fromEntries(numbers.map(([key]) => [key, number(form, key)])),
      qr_mode: string(form, 'qr_mode'), auto_verify_ok_scans: form.get('auto_verify_ok_scans') === 'on',
    },
  }))}>
    <p className="muted">Policy version {data.version}. Updates return active shifts to field review.</p>
    <div className="form-grid">
      {times.map(([key, label]) => <label key={key}>{label}<input type="time" name={key} defaultValue={settings[key].slice(0, 5)} required /></label>)}
      {numbers.map(([key, label, min, max, step]) => <label key={key}>{label}<input name={key} type="number"
        min={min} max={max} step={step} defaultValue={settings[key]} required /></label>)}
      <label>Allowed QR mode<select name="qr_mode" defaultValue={settings.qr_mode}><option value="dynamic">Dynamic</option><option value="static">Static</option><option value="both">Both</option></select></label>
    </div>
    <label className="check"><input name="auto_verify_ok_scans" type="checkbox" defaultChecked={settings.auto_verify_ok_scans} />Automatically verify complete clean shifts</label>
    <button className="primary">Save policy</button>
  </form>;
}

export function Administration({ organizationWide }: { organizationWide: boolean }) {
  const [tab, setTab] = useState('sites');
  const [rev, bump] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [credential, setCredential] = useState('');
  const [badge, setBadge] = useState<BadgeCode | null>(null);
  const sites = useApi<Site[]>('/sites', rev);
  const employees = useApi<Employee[]>(tab === 'employees' || tab === 'badges' ? '/employees' : null, rev);
  const terminals = useApi<Terminal[]>(tab === 'terminals' ? '/terminals' : null, rev);
  const users = useApi<StaffRow[]>(tab === 'users' ? '/users' : null, rev);
  const badges = useApi<Badge[]>(tab === 'badges' ? '/badges' : null, rev);
  const integrations = useApi<Integration[]>(tab === 'integrations' ? '/integrations/payroll' : null, rev);
  const rules = useApi<{ version: number; settings: Policy }>(tab === 'config' ? '/config' : null, rev);
  const siteList = sites.value || [];
  const isLoading = sites.loading || [employees, terminals, users, badges, rules, integrations].some((item) => item.loading);
  const loadingError = [sites, employees, terminals, users, badges, rules, integrations].find((item) => item.error)?.error;
  async function write(path: string, body?: object, method = 'PUT') {
    setBusy(true); setError(''); setNote(''); setCredential('');
    try {
      const result = await api<{ credential?: string }>(path, { method, body });
      if (result.credential) setCredential(result.credential);
      setNote('Saved.');
      bump((value) => value + 1);
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  const submit: Submit = (event, build) => {
    event.preventDefault();
    const payload = build(new FormData(event.currentTarget));
    void write(payload.path, payload.body);
  };
  async function image(id: string, file: File) {
    setError('');
    try {
      if (file.size > 64000) throw new Error('Use a JPEG smaller than 64 KB.');
      const bytes = new Uint8Array(await file.arrayBuffer());
      const jpeg = btoa(Array.from(bytes, (byte) => String.fromCharCode(byte)).join(''));
      await write(`/employees/${id}/badge-image`, { jpeg });
    } catch (cause) { setError((cause as Error).message); }
  }
  async function showBadge(id: string) {
    setError('');
    try { setBadge(await api<BadgeCode>(`/badges/${id}/code`)); }
    catch (cause) { setError((cause as Error).message); }
  }
  return <>
    <Heading title="Administration">Manage sites, employees, terminals and timekeeping policy.</Heading>
    <div className="tabs">{tabs.filter(([id]) => organizationWide || id !== 'integrations').map(([id, label]) => <button key={id} className={tab === id ? 'chosen' : ''} onClick={() => {
      setTab(id); setError(''); setNote(''); setCredential(''); setBadge(null);
    }}>{label}</button>)}</div>
    <ErrorNote text={error || loadingError} />
    {note && <p className="notice success" role="status">{note}</p>}
    {credential && <div className="notice warning terminal-credential"><KeyRound size={18} /><div><strong>{tab === 'integrations' ? 'Payroll API credential' : 'Terminal credential'}</strong>
      <p>{tab === 'integrations' ? 'Store this credential in the payroll integration. It is displayed once.' :
        'Copy this credential into the enrolled kiosk. It is displayed once.'}</p>
      <input readOnly value={credential} aria-label={tab === 'integrations' ? 'Payroll API credential' : 'Terminal credential'} onFocus={(event) => event.currentTarget.select()} />
    </div></div>}
    <section className="panel">
      <header className="panel-heading"><h2>{tabs.find(([id]) => id === tab)?.[1]}</h2>{isLoading && <Loading />}</header>
      <fieldset className="panel-body form-stack form-reset" disabled={busy || isLoading}>
        {tab === 'sites' && <SiteForm rows={siteList} submit={submit} />}
        {tab === 'employees' && <EmployeeForm rows={employees.value || []} sites={siteList} submit={submit} onImage={image} />}
        {tab === 'terminals' && <TerminalForm rows={terminals.value || []} sites={siteList} submit={submit} rotate={(code) => void write(`/terminals/${code}/rotate`, undefined, 'POST')} />}
        {tab === 'users' && <UserForm rows={users.value || []} sites={siteList} submit={submit} />}
        {tab === 'config' && rules.value && <PolicyForm key={rules.value.version} data={rules.value} submit={submit} />}
        {tab === 'integrations' && <form className="filters" onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          void write('/integrations/payroll', { name: string(data, 'integration_name'),
            site_id: string(data, 'site_id') || null }, 'POST');
        }}>
          <label>Integration name<input name="integration_name" required maxLength={120} /></label>
          <label>Site scope<select name="site_id"><option value="">Organization-wide</option><SiteOptions sites={siteList.filter((site) => site.active)} /></select></label>
          <button className="primary">Issue read-only credential</button>
        </form>}
        {tab === 'badges' && <form className="filters" onSubmit={(event) => {
          event.preventDefault(); const data = new FormData(event.currentTarget);
          void write('/badges/issue', { employee_id: string(data, 'employee_id'), mode: string(data, 'mode') }, 'POST');
        }}>
          <label>Employee<select name="employee_id" required><option value="">Select employee</option>{employees.value?.filter((row) => row.active).map((row) => <option key={row.id} value={row.id}>{row.name} · {row.id}</option>)}</select></label>
          <label>Badge mode<select name="mode"><option value="DYN">Dynamic</option><option value="STC">Static</option></select></label>
          <button className="primary"><QrCode size={16} />Issue badge</button>
        </form>}
      </fieldset>
      {tab === 'integrations' && (integrations.value?.length ? <div className="table-wrap"><table>
        <thead><tr><th>Integration</th><th>Scope</th><th>Status</th><th>Action</th></tr></thead>
        <tbody>{integrations.value.map((row) => <tr key={row.id}><td>{row.name}</td><td>{row.site_id || 'Organization-wide'}</td>
          <td>{row.revoked_at ? 'Revoked' : 'Active'}</td><td>{!row.revoked_at && <button className="secondary" disabled={busy}
            onClick={() => { if (window.confirm('Revoke this payroll API credential?')) void write(`/integrations/payroll/${row.id}/revoke`, undefined, 'POST'); }}>Revoke</button>}</td></tr>)}</tbody>
      </table></div> : <Empty>No payroll API credentials have been issued.</Empty>)}
      {tab === 'badges' && (badges.value?.length ? <div className="table-wrap"><table><thead><tr><th>Employee ID</th><th>Mode</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>{badges.value.map((row) => <tr key={row.id}><td>{row.employee_id}</td><td>{row.mode === 'DYN' ? 'Dynamic' : 'Static'}</td>
          <td>{row.revoked_at ? 'Revoked' : 'Active'}</td><td>{!row.revoked_at && <div className="actions">
            <button className="secondary" onClick={() => void showBadge(row.id)}>View QR</button>
            <button className="secondary" disabled={busy} onClick={() => { if (window.confirm('Revoke this badge?')) { setBadge(null); void write(`/badges/${row.id}/revoke`, undefined, 'POST'); } }}>Revoke</button>
          </div>}</td></tr>)}</tbody></table></div> : <Empty>No badges issued.</Empty>)}
    </section>
    {badge && <section className="panel badge-panel"><header className="panel-heading"><h2>Badge · {badge.employee_id}</h2><button className="secondary" onClick={() => setBadge(null)}>Close</button></header>
      <div className="panel-body"><BadgeImage badge={badge} />
        {badge.mode === 'STC' && <button className="secondary" onClick={() => saveLocal(`badge-${badge.employee_id}.svg`, 'image/svg+xml', badge.svg)}><Printer size={16} />Download printable badge</button>}</div></section>}
  </>;
}

function BadgeImage({ badge }: { badge: BadgeCode }) {
  const uri = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(badge.svg);
  return <img className="badge-code" alt={`QR badge for ${badge.employee_id}`} src={uri} />;
}

export function MyBadge() {
  const [rev, bump] = useState(0);
  const badge = useApi<BadgeCode>('/badges/mine', rev);
  useEffect(() => {
    if (!badge.value?.refresh_after_ms) return;
    const timer = window.setTimeout(() => bump((value) => value + 1), badge.value.refresh_after_ms + 100);
    return () => window.clearTimeout(timer);
  }, [badge.value]);
  return <>
    <Heading title="My badge">Present the rotating code at your registered gate.</Heading>
    <section className="panel badge-panel"><div className="panel-body">
      <ErrorNote text={badge.error} />{badge.loading && <Loading />}
      {badge.value && <><BadgeImage badge={badge.value} /><p>Employee ID {badge.value.employee_id}</p></>}
      <button className="secondary" onClick={() => bump(rev + 1)}>Refresh code</button>
    </div></section>
  </>;
}
