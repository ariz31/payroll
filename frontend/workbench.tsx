import { AlertTriangle, ArrowDown, ArrowRight, Check, Clock3, FileCheck2, ScanLine, Search } from 'lucide-react';
import { useMemo, useState, type FormEvent } from 'react';
import { API, api, query, stamp, type Metrics, type Session, type Shift, type Site } from './api';
import { Empty, ErrorNote, Heading, Loading, PeriodSite, Pill, useApi } from './common';

export interface Context {
  period: string;
  setPeriod: (value: string) => void;
  site: string;
  setSite: (value: string) => void;
  sites?: Site[];
  session: Session;
}

const actionNames: Record<string, string> = {
  endorse: 'Field endorsement', request_evidence: 'Evidence requested', cost_approve: 'Cost and overtime approved',
  cost_reject: 'Rejection recommended', return_foreman: 'Returned to foreman', return_engineer: 'Returned to engineer',
  verify: 'Verified', reject: 'Disputed / Rejected', reopen: 'Reopened', bulk_verify: 'Bulk verified',
  auto_verify: 'Automatically verified', policy_changed: 'Policy applied',
};
const stageNames: Record<string, string> = {
  foreman: 'Site foreman', engineer: 'Project engineer', timekeeper: 'Timekeeper',
  verified: 'Complete', disputed: 'Complete',
};

export function approvalName(action: string) {
  return actionNames[action] || action;
}

export function Overview(context: Context) {
  const { period, site, session } = context;
  const dashboard = useApi<Metrics>('/dashboard' + query({ period, site }));
  const recent = useApi<{ total: number; items: Shift[] }>('/shifts' + query({ period, site, limit: 8 }));
  const metrics = dashboard.value;
  const items = recent.value?.items || [];
  return <>
    <Heading title={session.role === 'employee' ? 'My overview' : 'Overview'} actions={<a className="button primary" href="#kiosk"><ScanLine size={17} /> Open kiosk</a>}>
      {session.role === 'employee' ? 'Your attendance and review status for the selected period.' : 'Monitor site attendance, verification and payroll readiness.'}
    </Heading>
    <PeriodSite {...context} />
    <ErrorNote text={dashboard.error || recent.error} />
    {dashboard.loading && <Loading />}
    {metrics && <>
      <div className="metrics">
        <Metric title={metrics.scan_scope === 'linked' ? 'Linked scans' : 'Scan attempts'} value={metrics.scanned} icon={<ScanLine />} />
        <Metric title="Verified shifts" value={metrics.verified} icon={<FileCheck2 />} tone="ok" />
        <Metric title="Pending review" value={metrics.pending} icon={<Clock3 />} tone="pending" />
        <Metric title="Disputed / Rejected" value={metrics.disputed} icon={<AlertTriangle />} tone="rejected" />
      </div>
      <section className="panel summary-strip" aria-label="Payroll metrics">
        <div><span>Missing clock-outs</span><strong>{metrics.missing_out}</strong></div>
        <div><span>Verified regular hours</span><strong>{metrics.verified_hours.regular_hours}</strong></div>
        <div><span>Verified overtime hours</span><strong>{metrics.verified_hours.ot_hours}</strong></div>
        <div><span>Employees on audit hold</span><strong>{metrics.audit_hold_employee_ids.length}</strong></div>
      </section>
    </>}
    <section className="panel">
      <header className="panel-heading"><div><h2>Period attendance</h2><p>Shift records and their current verification status.</p></div><a href="#verification" className="button secondary">View attendance <ArrowRight size={16} /></a></header>
      {recent.loading ? <Loading /> : items.length ? <ShiftTable rows={items} /> : <Empty>No shifts in this period.</Empty>}
    </section>
  </>;
}

function Metric({ title, value, icon, tone = '' }: { title: string; value: number; icon: React.ReactNode; tone?: string }) {
  return <div className="metric panel"><span className={`metric-icon ${tone}`}>{icon}</span><span>{title}</span><strong>{value.toLocaleString()}</strong></div>;
}

function ShiftTable({ rows, selected, toggle, sortable }: {
  rows: Shift[]; selected?: Set<string>; toggle?: (id: string) => void; sortable?: boolean;
}) {
  const [order, setOrder] = useState<{ key: 'date' | 'name' | 'status'; desc: boolean }>({ key: 'date', desc: true });
  const ordered = useMemo(() => {
    const key = order.key === 'date' ? 'work_date' : order.key;
    return [...rows].sort((a, b) => a[key].localeCompare(b[key]) * (order.desc ? -1 : 1));
  }, [rows, order]);
  const header = (key: 'date' | 'name' | 'status', label: string) => sortable
    ? <button className="sort" onClick={() => setOrder({ key, desc: key === order.key ? !order.desc : false })}>
      {label}{order.key === key && <ArrowDown size={13} className={order.desc ? '' : 'ascending'} />}</button> : label;
  return <div className="table-wrap"><table>
    <thead><tr>{toggle && <th><span className="sr-only">Select</span></th>}<th>{header('name', 'Employee')}</th>
      <th>{header('date', 'Work date')}</th><th>Shift</th><th>Exception</th><th>{header('status', 'Status')}</th><th><span className="sr-only">Details</span></th></tr></thead>
    <tbody>{ordered.map((row) => <tr key={row.id}>
      {toggle && <td>{row.stage === 'foreman' && row.raw_in && row.raw_out && row.anomaly === 'OK' &&
        <input type="checkbox" checked={selected?.has(row.id) || false} onChange={() => toggle(row.id)} aria-label={`Select ${row.name} ${row.work_date}`} />}</td>}
      <td><strong>{row.name}</strong><small>{row.employee_id} · {row.site_id}</small></td><td>{row.work_date}</td><td>{row.shift_type}</td>
      <td>{row.open_shift ? 'Awaiting clock-out' : row.anomaly}</td><td><Pill status={row.status} /></td>
      <td><a className="text-link" href={`#verification/${row.id}`} aria-label={`View ${row.name} ${row.work_date}`}>View <ArrowRight size={15} /></a></td>
    </tr>)}</tbody>
  </table></div>;
}

function queueAction(e: FormEvent<HTMLFormElement>, callback: (data: FormData) => void) {
  e.preventDefault();
  callback(new FormData(e.currentTarget));
}

export function Verification(context: Context & { selected?: string }) {
  const { selected, session, period, site } = context;
  const [status, setStatus] = useState('');
  const [anomaly, setAnomaly] = useState('');
  const [employee, setEmployee] = useState('');
  const [advanced, setAdvanced] = useState(false);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(0);
  const [checked, setChecked] = useState(new Set<string>());
  const [rev, bump] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const limit = 30;
  const data = useApi<{ total: number; items: Shift[] }>(!selected ? '/shifts' + query({
    period, site, status, anomaly, employee, ...filters, limit, offset: page * limit,
  }) : null, rev);
  if (selected) return <ShiftDetail key={selected} ident={selected} session={session} period={period} />;
  const rows = data.value?.items || [];
  const chosen = rows.filter((row) => checked.has(row.id));
  const resetPage = () => { setPage(0); setChecked(new Set()); setNotice(''); };
  async function bulk() {
    setBusy(true); setError(''); setNotice('');
    try {
      await api('/shifts/bulk-verify', { method: 'POST', body: {
        request_id: crypto.randomUUID(), items: chosen.map(({ id, version }) => ({ id, version })),
      } });
      setNotice(`${chosen.length} clean shifts verified.`);
      setChecked(new Set());
      bump(rev + 1);
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  return <>
    <Heading title={session.role === 'employee' ? 'My attendance' : 'Verification'}>Review punches, exceptions and shift approvals.</Heading>
    <section className="panel">
      <div className="filter-panel">
        <PeriodSite {...context} setPeriod={(value) => { context.setPeriod(value); resetPage(); }}
          setSite={(value) => { context.setSite(value); resetPage(); }} />
        <div className="filters">
          <label>Status<select value={status} onChange={(e) => { setStatus(e.target.value); resetPage(); }}><option value="">All statuses</option>
            {['Pending Review', 'Verified', 'Disputed / Rejected'].map((value) => <option key={value}>{value}</option>)}</select></label>
          <label>Exception<select value={anomaly} onChange={(e) => { setAnomaly(e.target.value); resetPage(); }}><option value="">All exceptions</option>
            {['MISSING QR OUT', 'MISSING QR IN', 'LATE (>5m)', 'HIGH OT (>2h)', 'OK'].map((value) => <option key={value}>{value}</option>)}</select></label>
          {session.role !== 'employee' && <form className="search" onSubmit={(event) => queueAction(event, (data) => {
            setEmployee(String(data.get('employee')).trim()); resetPage();
          })}><label>Employee ID<input name="employee" placeholder="Find by employee ID" /></label>
            <button className="button secondary" aria-label="Search by employee ID"><Search size={17} /></button></form>}
          <button className="button secondary" onClick={() => setAdvanced(!advanced)}>{advanced ? 'Hide filters' : 'More filters'}</button>
        </div>
        {advanced && <form className="filters" onSubmit={(event) => queueAction(event, (data) => {
          setFilters(Object.fromEntries([...data].map(([key, value]) => [key, String(value).trim()]))); resetPage();
        })}>
          <label>Project / cost code<input name="cost_code" defaultValue={filters.cost_code} /></label>
          <label>Department<input name="department" defaultValue={filters.department} /></label>
          <label>Work date<input name="work_date" type="date" defaultValue={filters.work_date} /></label>
          <label>Shift type<select name="shift_type" defaultValue={filters.shift_type}><option value="">All shifts</option><option>Day Shift</option><option>Night Shift</option></select></label>
          <label>Review stage<select name="stage" defaultValue={filters.stage}><option value="">All stages</option>{Object.keys(stageNames).slice(0, 3).map((key) => <option key={key} value={key}>{stageNames[key]}</option>)}</select></label>
          <button className="button secondary">Apply filters</button>
        </form>}
      </div>
      <ErrorNote text={error || data.error} />
      {notice && <p className="notice success" role="status"><Check size={17} />{notice}</p>}
      {chosen.length > 0 && <div className="bulk"><span>{chosen.length} clean shifts selected</span><button className="primary" onClick={bulk} disabled={busy}>Verify selected</button></div>}
      {data.loading ? <Loading /> : rows.length ? <ShiftTable rows={rows} selected={checked} sortable
        toggle={session.role === 'timekeeper' ? (id) => setChecked((previous) => {
          const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next;
        }) : undefined} /> : <Empty>No shifts match these filters.</Empty>}
      <footer className="pager"><span>{data.value?.total ?? 0} shifts</span><div><button className="secondary" disabled={page === 0} onClick={() => { setPage(page - 1); setChecked(new Set()); }}>Previous</button>
        <button className="secondary" disabled={(page + 1) * limit >= (data.value?.total ?? 0)} onClick={() => { setPage(page + 1); setChecked(new Set()); }}>Next</button></div></footer>
    </section>
  </>;
}

function actionsFor(row: Shift, session: Session) {
  if (session.role === 'foreman' && row.stage === 'foreman') return row.open_shift ? ['request_evidence'] : ['endorse', 'request_evidence'];
  if (session.role === 'engineer' && row.stage === 'engineer') return ['cost_approve', 'cost_reject', 'return_foreman'];
  if (session.role !== 'timekeeper') return [];
  if (row.stage === 'timekeeper') return ['verify', 'reject', 'return_engineer'];
  if (row.stage === 'verified' || row.stage === 'disputed') return ['reopen'];
  return [];
}

function ShiftDetail({ ident, session, period }: { ident: string; session: Session; period: string }) {
  const [rev, bump] = useState(0);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [action, setAction] = useState('');
  const [busy, setBusy] = useState(false);
  const data = useApi<Shift>(`/shifts/${ident}`, rev);
  const row = data.value;
  const actions = row ? actionsFor(row, session) : [];
  const currentAction = actions.includes(action) ? action : actions[0];
  const canAdjust = currentAction === 'verify' || currentAction === 'reject';
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!row || !currentAction) return;
    const values = new FormData(event.currentTarget);
    const convert = (value: FormDataEntryValue | null) => {
      const text = String(value || '').trim();
      if (text && (!/(?:Z|[+-]\d\d:\d\d)$/.test(text) || Number.isNaN(Date.parse(text)))) {
        throw new Error('Use an ISO date and time with an offset, for example 2026-11-12T17:00:00+08:00.');
      }
      return text || null;
    };
    setError(''); setSuccess(''); setBusy(true);
    try {
      await api(`/shifts/${row.id}/review`, { method: 'POST', body: {
        action: currentAction, version: row.version, request_id: crypto.randomUUID(),
        notes: String(values.get('notes')).trim(), adjusted_in: convert(values.get('adjusted_in')),
        adjusted_out: convert(values.get('adjusted_out')),
      } });
      setSuccess('Review saved.');
      bump(rev + 1);
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  return <>
    <a className="text-link back" href="#verification">← Return to attendance</a>
    {data.loading && <Loading />}
    <ErrorNote text={data.error || error} />
    {success && <p className="notice success" role="status">{success}</p>}
    {row && <>
      <Heading title={row.name} actions={<Pill status={row.status} />}>{row.employee_id} · {row.work_date} · {row.shift_type} · {row.site_id}</Heading>
      <section className="panel">
        <header className="panel-heading"><div><h2>Punch evidence</h2><p>{row.timezone} · Terminal {row.terminal_code}</p></div></header>
        <div className="table-wrap"><table><thead><tr><th>Time</th><th>Raw punch</th><th>Adjustment</th><th>Effective</th></tr></thead>
          <tbody>{(['in', 'out'] as const).map((name) => <tr key={name}><th>Clock-{name}</th>
            <td>{stamp(row[`raw_${name}`], row.timezone, true)}</td><td>{stamp(row[`adjusted_${name}`], row.timezone, true)}</td>
            <td>{stamp(row[`effective_${name}`], row.timezone, true)}</td></tr>)}</tbody></table></div>
        <div className="inline-details"><span>Exception <strong>{row.open_shift ? 'Awaiting clock-out' : row.anomaly}</strong></span><span>Cost code <strong>{row.cost_code}</strong></span>
          <span>Break <strong>{row.break_mins} min</strong></span><span>Regular <strong>{row.regular_hours} h</strong></span><span>Overtime <strong>{row.ot_hours} h</strong></span>
          <span>Night <strong>{row.night_hours} h</strong></span></div>
        <p className="inline-details">Shift ID <code>{row.id}</code></p>
      </section>
      {!!(row.evidence?.badge || row.evidence?.scans.length) && <section className="panel">
        <header className="panel-heading"><h2>Retained images</h2></header><div className="image-grid">
          {(['badge', 'in', 'out'] as const).filter((kind) => kind === 'badge' ? row.evidence?.badge :
            row.evidence?.scans.includes(row[`${kind}_event`] || '')).map((kind) =>
            <figure key={kind}><img src={`${API}/shifts/${row.id}/evidence/${kind}`} alt={kind === 'badge' ? 'Registered badge' : `Clock-${kind} evidence`} loading="lazy" />
              <figcaption>{kind === 'badge' ? 'Badge image' : `Clock-${kind} image`}</figcaption></figure>)}
        </div>
      </section>}
      {currentAction && <section className="panel">
        <header className="panel-heading"><div><h2>Record a review</h2><p>Current stage · {stageNames[row.stage]}</p></div></header>
        <form className="panel-body form-stack" onSubmit={save}>
          <label>Action<select value={currentAction} onChange={(event) => setAction(event.target.value)}>
            {actions.map((value) => <option key={value} value={value}>{approvalName(value)}</option>)}</select></label>
          {canAdjust && <div className="form-grid">
            <label>Adjusted clock-in (optional)<input name="adjusted_in" placeholder={`${row.work_date}T08:00:00+08:00`} /></label>
            <label>Adjusted clock-out (optional)<input name="adjusted_out" placeholder={`${row.work_date}T17:00:00+08:00`} /></label>
          </div>}
          <label>Reason and evidence<textarea name="notes" required maxLength={1500} rows={3} /></label>
          <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save review'}</button>
        </form>
      </section>}
      {!!row.reconciled_scans?.length && <section className="panel">
        <header className="panel-heading"><h2>Linked quarantined scans</h2></header>
        <ol className="history">{row.reconciled_scans.map((entry) => <li key={entry.event_id}>
          <strong>{entry.actor_login}</strong><span>{stamp(entry.decided_at, row.timezone, true)}</span><p>{entry.notes}</p>
        </li>)}</ol>
      </section>}
      {row.history && <section className="panel"><header className="panel-heading"><h2>Review history</h2></header>
        {row.history.length ? <ol className="history">{row.history.map((entry) => <li key={entry.id}>
          <strong>{approvalName(entry.action)}</strong><span>{entry.actor_name} · {stamp(entry.occurred_at, row.timezone, true)}</span><p>{entry.reason}</p>
        </li>)}</ol> : <Empty>No review decisions yet.</Empty>}
      </section>}
      {['employee', 'auditor', 'timekeeper'].includes(session.role) &&
        <a href={`#print/${row.work_date.slice(0, 7) || period}/${row.employee_id}`} className="button secondary">Print daily time record</a>}
    </>}
  </>;
}
