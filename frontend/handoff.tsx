import { AlertTriangle, Download, FileSpreadsheet, Printer } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { API, api, query, stamp, type Approval, type AuditScan, type ControlAudit, type ExportRevision, type Session, type Summary } from './api';
import { Empty, ErrorNote, Heading, Loading, PeriodSite, useApi } from './common';
import { approvalName, type Context } from './workbench';

export function Payroll(context: Context) {
  const { period, site, session } = context;
  const [rev, bump] = useState(0);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [employee, setEmployee] = useState('');
  const preview = useApi<Summary>(`/payroll/periods/${period}/preflight` + query({ site }), rev);
  const revisions = useApi<ExportRevision[]>('/payroll/exports' + query({ period }), rev);
  const summary = preview.value;
  async function generate(format: 'csv' | 'xlsx') {
    if (!summary) return;
    setBusy(true); setNote(''); setError('');
    try {
      const receipt = await api<ExportRevision>('/payroll/exports', {
        method: 'POST', body: { period, format, site: site || null, expected_pending_count: summary.pending, snapshot_key: summary.snapshot_key },
      });
      setNote(`Revision ${receipt.revision} is ready to download.`);
      bump(rev + 1);
    } catch (cause) { setError((cause as Error).message); bump(rev + 1); }
    finally { setBusy(false); }
  }
  return <>
    <Heading title="Payroll exports">Prepare the period attendance file and review release holds.</Heading>
    <PeriodSite {...context} />
    <ErrorNote text={error || preview.error || revisions.error} />
    {note && <p role="status" className="notice success">{note}</p>}
    {preview.loading && <Loading />}
    {summary && <>
      {summary.audit_hold_employee_ids.length > 0 && <p className="notice warning"><AlertTriangle size={18} /><span>
        <strong>{summary.audit_hold_employee_ids.length} employees on audit hold.</strong> Held IDs {summary.audit_hold_employee_ids.join(', ')}.
      </span></p>}
      <section className="panel">
        <header className="panel-heading"><div><h2>Period preflight</h2><p>{summary.row_count} shift records · {summary.pending} pending review · {summary.disputed} disputed</p></div>
          {session.role === 'timekeeper' && <div className="actions"><button className="secondary" disabled={busy || !summary.row_count} onClick={() => generate('csv')}>Generate CSV</button>
            <button className="primary" disabled={busy || !summary.row_count} onClick={() => generate('xlsx')}><FileSpreadsheet size={16} />Generate XLSX</button></div>}
        </header>
        <div className="table-wrap"><table><thead><tr><th>Hours</th><th>Regular</th><th>Overtime</th><th>Night</th></tr></thead>
          <tbody><tr><th>Verified</th><td>{summary.verified_hours.regular_hours}</td><td>{summary.verified_hours.ot_hours}</td><td>{summary.verified_hours.night_hours}</td></tr>
            <tr><th>Eligible for release</th><td>{summary.releasable_hours.regular_hours}</td><td>{summary.releasable_hours.ot_hours}</td><td>{summary.releasable_hours.night_hours}</td></tr></tbody>
        </table></div>
      </section>
    </>}
    <section className="panel"><header className="panel-heading"><div><h2>Export revisions</h2><p>Recorded files, reviewer and checksums.</p></div></header>
      {revisions.loading ? <Loading /> : revisions.value?.length ? <div className="table-wrap"><table>
        <thead><tr><th>Revision</th><th>Scope</th><th>Created</th><th>By</th><th>Checksum</th><th>File</th></tr></thead>
        <tbody>{revisions.value.map((item) => <tr key={item.id}><td>Revision {item.revision}</td><td>{item.site_id || 'Organization'}</td>
          <td>{stamp(item.created_at, undefined, true)}</td><td>{item.actor_name}</td><td><code title={item.digest}>{item.digest.slice(0, 12)}…</code></td>
          <td><a className="text-link" href={`${API}/payroll/exports/${item.id}?download=true`}><Download size={16} />{item.format.toUpperCase()}</a>
            <a className="text-link receipt" href={`${API}/payroll/exports/${item.id}`} target="_blank" rel="noreferrer">Receipt</a></td></tr>)}</tbody>
      </table></div> : <Empty>No exports have been created for this period.</Empty>}
    </section>
    <section className="panel"><header className="panel-heading"><div><h2>Daily time record</h2><p>Print a Form 48 draft for an employee.</p></div></header>
      <form className="panel-body filters" onSubmit={(event) => {
        event.preventDefault(); location.hash = `print/${period}/${encodeURIComponent(employee.trim())}`;
      }}><label>Employee ID<input value={employee} onChange={(event) => setEmployee(event.target.value)} required /></label>
        <button className="secondary"><Printer size={16} />Open print view</button></form>
    </section>
  </>;
}

export function Audit({ session }: { session: Session }) {
  const [tab, setTab] = useState(['foreman', 'engineer'].includes(session.role) ? 'approvals' : 'scans');
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState('');
  const [site, setSite] = useState('');
  const [unresolved, setUnresolved] = useState(false);
  const [selected, setSelected] = useState<AuditScan | null>(null);
  const [revision, setRevision] = useState(0);
  const scans = useApi<AuditScan[]>(tab === 'scans' ? '/audit/scans' + query({ result, site, offset, limit: 50, unresolved: unresolved ? 'true' : undefined }) : null, revision);
  const approvals = useApi<Approval[]>(tab === 'approvals' ? '/audit/approvals' + query({ offset, limit: 50 }) : null);
  const controls = useApi<ControlAudit[]>(tab === 'control' ? '/audit/control' + query({ offset, limit: 50 }) : null);
  const data = tab === 'approvals' ? approvals : tab === 'control' ? controls : scans;
  const switchTab = (value: string) => { setTab(value); setOffset(0); setSelected(null); };
  function applyFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSite(String(new FormData(event.currentTarget).get('site')).trim()); setOffset(0);
  }
  return <>
    <Heading title="Audit trail">Inspect scan outcomes and recorded decisions in your scope.</Heading>
    <div className="tabs">
      {!['foreman', 'engineer'].includes(session.role) && <button className={tab === 'scans' ? 'chosen' : ''} onClick={() => switchTab('scans')}>Scan ledger</button>}
      <button className={tab === 'approvals' ? 'chosen' : ''} onClick={() => switchTab('approvals')}>Approval history</button>
      {['admin', 'auditor'].includes(session.role) && !session.site_id &&
        <button className={tab === 'control' ? 'chosen' : ''} onClick={() => switchTab('control')}>Administrative events</button>}
    </div>
    <section className="panel">
      {tab === 'scans' && <form className="panel-body filters" onSubmit={applyFilter}>
        <label>Outcome<select value={result} onChange={(event) => { setResult(event.target.value); setOffset(0); }}>
          <option value="">All outcomes</option>{['ACCEPTED_IN', 'ACCEPTED_OUT', 'IGNORED_DEBOUNCE', 'REJECTED', 'QUARANTINED'].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Site code<input name="site" /></label>
        <label className="check"><input type="checkbox" checked={unresolved} onChange={(event) => {
          setUnresolved(event.target.checked); setResult(''); setOffset(0);
        }} />Unresolved quarantine</label><button className="secondary">Apply filter</button>
      </form>}
      <ErrorNote text={data.error} />
      {data.loading ? <Loading /> : !data.value?.length ? <Empty>No matching events.</Empty> : <div className="table-wrap">
        {tab === 'scans' && <table><thead><tr><th>Received</th><th>Reported</th><th>Terminal</th><th>Employee</th><th>Outcome</th><th>Reason</th><th>Sequence</th><th>Reconciliation</th></tr></thead>
          <tbody>{scans.value?.map((row) => <tr key={row.id}><td>{stamp(row.received_at, undefined, true)}</td><td>{stamp(row.reported_at, undefined, true)}</td>
            <td>{row.terminal_code}<small>{row.site_id}</small></td><td>{row.employee_id || '—'}</td><td>{row.result}</td><td>{row.reason || '—'}</td><td>{row.sequence ?? '—'}</td><td>{row.disposition
                ? <><span>{row.disposition === 'dismissed' ? 'Dismissed' : 'Linked for review'}</span>
                  <small>{row.actor_login} · {row.reconciliation_notes}</small>
                  {row.linked_shift && <a href={`#verification/${row.linked_shift}`}>View linked shift</a>}</>
                : row.result === 'QUARANTINED' && session.role === 'timekeeper'
                  ? <button className="secondary" onClick={() => setSelected(row)}>Reconcile</button> : '—'}</td></tr>)}</tbody></table>}
        {tab === 'approvals' && <table><thead><tr><th>Recorded</th><th>Employee</th><th>Action</th><th>Actor</th><th>Reason</th></tr></thead>
          <tbody>{approvals.value?.map((row) => <tr key={row.id}><td>{stamp(row.occurred_at, undefined, true)}</td>
            <td><a href={`#verification/${row.shift_id}`}>{row.employee_id}</a><small>{row.site_id}</small></td><td>{approvalName(row.action)}</td><td>{row.actor_name}</td><td>{row.reason}</td></tr>)}</tbody></table>}
        {tab === 'control' && <table><thead><tr><th>Recorded</th><th>Action</th><th>Object</th><th>Actor</th></tr></thead>
          <tbody>{controls.value?.map((row) => <tr key={row.id}><td>{stamp(row.occurred_at, undefined, true)}</td>
            <td>{row.action}</td><td>{row.object_id}</td><td>{row.login || 'System'}</td></tr>)}</tbody></table>}
      </div>}
      <footer className="pager"><span>{offset ? `From record ${offset + 1}` : 'Latest events'}</span><div>
        <button className="secondary" disabled={!offset} onClick={() => setOffset(offset - 50)}>Previous</button>
        <button className="secondary" disabled={(data.value?.length || 0) < 50} onClick={() => setOffset(offset + 50)}>Next</button></div></footer>
    </section>
    {selected && tab === 'scans' && <ReconcileForm key={selected.id} row={selected}
      cancel={() => setSelected(null)} saved={() => { setSelected(null); setRevision((value) => value + 1); }} />}
  </>;
}

function ReconcileForm({ row, cancel, saved }: { row: AuditScan; cancel: () => void; saved: () => void }) {
  const [disposition, setDisposition] = useState(row.shift_id ? 'linked_for_review' : 'dismissed');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setBusy(true); setError('');
    try {
      await api(`/audit/scans/${row.id}/reconcile`, { method: 'POST', body: {
        disposition, notes: String(values.get('notes')).trim(),
        shift_id: disposition === 'linked_for_review' ? String(values.get('shift_id')).trim() : null,
      } });
      saved();
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  return <section className="panel">
    <header className="panel-heading"><div><h2>Reconcile quarantined scan</h2><p>{row.terminal_code} · {row.reason}</p></div></header>
    <ErrorNote text={error} />
    <form className="panel-body form-stack" onSubmit={submit}>
      <label>Decision<select value={disposition} onChange={(event) => setDisposition(event.target.value)}>
        <option value="dismissed">Dismiss with reason</option><option value="linked_for_review">Link to pending shift</option></select></label>
      {disposition === 'linked_for_review' && <label>Pending shift ID<input name="shift_id" defaultValue={row.shift_id || ''} required /></label>}
      <label>Reason and evidence<textarea name="notes" maxLength={1500} rows={3} required /></label>
      <div className="actions"><button className="primary" disabled={busy}>Save reconciliation</button>
        <button type="button" className="secondary" onClick={cancel}>Cancel</button></div>
    </form>
  </section>;
}

interface RecordDay {
  day: number;
  am_in?: string;
  am_out?: string;
  pm_in?: string;
  pm_out?: string;
  note?: string;
  overnight?: { in?: string; out?: string };
}

interface DailyRecord { name: string; employee_id: string; department: string; period: string; days: RecordDay[]; audit_hold: boolean }

export function PrintRecord({ path }: { path: string }) {
  const [, period, employee] = path.split('/');
  const response = useApi<DailyRecord>(period && employee ? `/payroll/periods/${period}/dtr/${employee}` : null);
  const data = response.value;
  if (!data) return <main className="dtr"><a href="#verification">Return to attendance</a><ErrorNote text={response.error} />{response.loading && <Loading />}</main>;
  const overnight = data.days.filter((day) => day.overnight || day.note);
  return <main className="dtr">
    <div className="print-actions"><a href="#verification">Return to attendance</a><button className="primary" onClick={() => window.print()}><Printer size={16} /> Print record</button></div>
    <article>
      <p>Civil Service Form No. 48 · Draft for agency review</p><h1>Daily time record</h1>
      <dl className="dtr-meta"><div><dt>Employee</dt><dd>{data.name} · {data.employee_id}</dd></div><div><dt>Department</dt><dd>{data.department}</dd></div>
        <div><dt>For the month of</dt><dd>{data.period}</dd></div><div><dt>Official hours (regular days / Saturdays)</dt><dd>__________________</dd></div></dl>
      {data.audit_hold && <p className="dtr-note"><strong>AUDIT HOLD</strong> · Pending attendance exists for this period.</p>}
      <table><thead><tr><th rowSpan={2}>Day</th><th colSpan={2}>A.M.</th><th colSpan={2}>P.M.</th><th colSpan={2}>Undertime</th></tr>
        <tr>{['Arrival', 'Departure', 'Arrival', 'Departure', 'Hours', 'Minutes'].map((label, index) => <th key={index}>{label}</th>)}</tr></thead>
        <tbody>{data.days.map((day) => <tr key={day.day}><td>{day.day}</td>{[day.am_in, day.am_out, day.pm_in, day.pm_out, '', ''].map((time, index) => <td key={index}>{time}</td>)}</tr>)}</tbody>
      </table>
      <p className="dtr-note">Verified gate punches are populated. Lunch punches and undertime are left for agency completion.</p>
      {overnight.length > 0 && <section className="dtr-notes"><h2>Overnight shifts and unresolved records</h2><ul>{overnight.map((day) =>
        <li key={day.day}>Day {day.day} · {day.note || [day.overnight?.in, day.overnight?.out].filter(Boolean).join(' to ')}</li>)}</ul></section>}
      <div className="signatures"><span>Employee signature</span><span>Authorized reviewer</span></div>
    </article>
  </main>;
}
