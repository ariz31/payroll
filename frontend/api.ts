export const API = '/api/v1';

export type Role = 'admin' | 'foreman' | 'engineer' | 'timekeeper' | 'auditor' | 'employee';
export type ShiftType = 'Day Shift' | 'Night Shift';
export type Status = 'Pending Review' | 'Verified' | 'Disputed / Rejected';

export interface Session {
  id: string;
  org_id: string;
  login: string;
  name: string;
  role: Role;
  site_id: string | null;
  scope_code: string | null;
  employee_id: string | null;
}

export interface Site {
  id: string;
  name: string;
  timezone: string;
  latitude: number;
  longitude: number;
  radius_m: number;
  active: boolean;
  evidence_mode: 'off' | 'optional' | 'required';
  evidence_notice: string;
  evidence_days: number;
}

export interface Shift {
  id: string;
  name: string;
  employee_id: string;
  site_id: string;
  cost_code: string;
  department: string;
  crew: string;
  work_date: string;
  timezone: string;
  shift_type: ShiftType;
  raw_in: string | null;
  raw_out: string | null;
  adjusted_in: string | null;
  adjusted_out: string | null;
  effective_in: string | null;
  effective_out: string | null;
  regular_hours: string;
  ot_hours: string;
  night_hours: string;
  net_hours: string;
  break_mins: number;
  open_shift: boolean;
  anomaly: string;
  stage: 'foreman' | 'engineer' | 'timekeeper' | 'verified' | 'disputed';
  status: Status;
  terminal_code: string;
  version: number;
  notes?: string;
  history?: Approval[];
  reconciled_scans?: { event_id: string; actor_login: string; decided_at: string; notes: string }[];
  evidence?: { badge: boolean; scans: string[] };
  in_event: string | null;
  out_event: string | null;
}

export interface Approval {
  id: number;
  actor_name: string;
  occurred_at: string;
  action: string;
  reason: string;
  shift_id?: string;
  employee_id?: string;
  site_id?: string;
}

export interface AuditScan {
  id: string;
  terminal_code: string;
  employee_id: string | null;
  site_id: string;
  result: string;
  reason: string;
  received_at: string;
  reported_at: string;
  sequence: number | null;
  shift_id: string | null;
  disposition: 'dismissed' | 'linked_for_review' | null;
  linked_shift: string | null;
  actor_login: string | null;
  reconciliation_notes: string | null;
}

export interface ControlAudit {
  id: number;
  login: string | null;
  action: string;
  object_id: string;
  occurred_at: string;
}

export interface Hours {
  regular_hours: string;
  ot_hours: string;
  night_hours: string;
}

export interface Summary {
  verified: number;
  pending: number;
  disputed: number;
  missing_out: number;
  row_count: number;
  audit_hold_employee_ids: string[];
  verified_hours: Hours;
  releasable_hours: Hours;
  policy_versions: number[];
  snapshot_key: string;
}

export interface Metrics extends Summary {
  scanned: number;
  quarantined: number;
  rejected: number;
  scan_scope: string;
}

export interface ExportRevision {
  id: string;
  site_id: string | null;
  period: string;
  revision: number;
  format: 'csv' | 'xlsx';
  actor_name: string;
  created_at: string;
  digest: string;
  signed_receipt: string;
  snapshot: Summary;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, options: { method?: string; body?: object } = {}): Promise<T> {
  const { method = 'GET', body } = options;
  let response: Response;
  try {
    response = await fetch(API + path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(25000),
    });
  } catch {
    throw new ApiError(0, 'Could not reach SiteGuard. Check your connection and try again.');
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('siteguard:signout'));
    const detail = payload?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item: { loc: string[]; msg: string }) => `${item.loc.at(-1)}: ${item.msg}`).join(' ')
      : detail;
    throw new ApiError(response.status, message || 'SiteGuard could not process this request.');
  }
  if (payload === null) throw new ApiError(502, 'SiteGuard returned an unexpected response.');
  return payload;
}

export function query(values: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(values)) if (value !== undefined && value !== '') params.set(name, String(value));
  const string = params.toString();
  return string ? '?' + string : '';
}

export function periodNow() {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit' }).format(new Date());
}

export function stamp(value: string | null, timezone?: string, date = false) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit', minute: '2-digit', timeZone: timezone,
    ...(date ? { day: '2-digit', month: 'short', year: 'numeric' } : {}),
  }).format(new Date(value));
}
