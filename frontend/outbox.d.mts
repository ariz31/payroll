export class NetworkError extends Error {}
export interface TerminalStatus {
  code?: string;
  site?: string;
  evidenceMode?: 'off' | 'optional' | 'required';
  evidenceNotice?: string;
  expires?: number;
  queued: number;
  quarantined: number;
}
export interface Receipt {
  id: string;
  client_event_id: string;
  sequence: number | null;
  event_hash: string;
  result: 'ACCEPTED_IN' | 'ACCEPTED_OUT' | 'IGNORED_DEBOUNCE' | 'REJECTED' | 'QUARANTINED';
  chain_advanced: boolean;
}
export function enroll(credential: string): Promise<TerminalStatus>;
export function terminalStatus(): Promise<TerminalStatus>;
export function refreshTerminal(): Promise<TerminalStatus>;
export function queueScan(qr: string, direction: 'auto' | 'in' | 'out', location: GeolocationCoordinates | null, jpeg: string, captured?: number): Promise<{ eventId: string; leaseValid: boolean }>;
export function flush(): Promise<Receipt[]>;
export function quarantineReceipts(): Promise<object[]>;
export function clearQuarantine(): Promise<TerminalStatus>;
