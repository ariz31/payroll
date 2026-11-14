const DATABASE = 'siteguard-terminal-v1';
const text = new TextEncoder();

export class NetworkError extends Error {}

function request(result) {
  return new Promise((resolve, reject) => {
    result.onsuccess = () => resolve(result.result);
    result.onerror = () => reject(result.error);
  });
}

function done(transaction) {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = resolve;
    transaction.onabort = () => reject(transaction.error);
    transaction.onerror = () => reject(transaction.error);
  });
}

async function open() {
  const database = indexedDB.open(DATABASE, 1);
  database.onupgradeneeded = () => {
    database.result.createObjectStore('terminal');
    database.result.createObjectStore('outbox', { keyPath: 'sequence' });
  };
  return request(database);
}

function exclusive(action) {
  if (!navigator.locks || !crypto.subtle) {
    throw new Error('The kiosk needs a secure browser with Web Locks support.');
  }
  return navigator.locks.request(DATABASE, async () => {
    const database = await open();
    try {
      return await action(database);
    } finally {
      database.close();
    }
  });
}

async function read(database) {
  const transaction = database.transaction(['terminal', 'outbox']);
  return Promise.all([
    request(transaction.objectStore('terminal').get('state')),
    request(transaction.objectStore('outbox').getAll()),
  ]);
}

function save(database, state, append, acknowledged = [], quarantined = []) {
  const transaction = database.transaction(['terminal', 'outbox'], 'readwrite', { durability: 'strict' });
  const saved = done(transaction);
  transaction.objectStore('terminal').put(state, 'state');
  if (append) transaction.objectStore('outbox').add(append);
  for (const sequence of acknowledged) transaction.objectStore('outbox').delete(sequence);
  for (const entry of quarantined) transaction.objectStore('outbox').put({ ...entry, quarantined: true });
  return saved;
}

function hex(buffer) {
  return Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function canonical(event) {
  return JSON.stringify([
    1, event.client_event_id, event.generation, event.sequence, event.captured_ms,
    event.latitude_e6, event.longitude_e6, event.accuracy_mm, event.direction,
    event.qr_payload, event.jpeg, event.lease, event.previous_hash,
  ]);
}

async function encrypt(key, value) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, text.encode(value));
  return { iv, data };
}

async function decrypt(key, { iv, data }) {
  return new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, data));
}

async function api(path, credential, body) {
  let response;
  try {
    response = await fetch('/api/v1' + path, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: 'Device ' + credential },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(9000),
    });
  } catch {
    throw new NetworkError('Could not reach the attendance server.');
  }
  if (response.status === 502 || response.status === 503 || response.status === 504) {
    throw new NetworkError('The attendance server is temporarily unavailable.');
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'The attendance server could not process the request.');
  }
  return response.json();
}

function clock(state) {
  return Date.now() + state.clockOffset;
}

function nextClock(previous, status, clientMs) {
  const offset = status.issued_ms - clientMs;
  if (previous && Math.abs(previous.clockOffset - offset) > 90000) {
    throw new Error('Terminal clock changed. Contact your supervisor before continuing.');
  }
  return offset;
}

async function establish(database, credential, state, entries) {
  const clientMs = Date.now();
  const status = await api('/terminals/session', credential, { client_ms: clientMs });
  if (state && entries.some((entry) => !entry.quarantined) &&
      (state.terminal_id !== status.terminal_id || state.generation !== status.generation)) {
    throw new Error('An earlier enrollment has unsynced scans. Contact your supervisor before enrolling this device.');
  }
  if (state && state.terminal_id !== status.terminal_id && entries.length) {
    throw new Error('Archive the existing quarantined records before switching terminals.');
  }
  const same = state?.terminal_id === status.terminal_id && state.generation === status.generation;
  const key = same ? state.key : await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
  if (!same && entries.length) {
    throw new Error('Archive the existing quarantined records before changing enrollment.');
  }
  const pending = entries.filter((entry) => !entry.quarantined);
  // If the server accepted a batch and its response was lost, leave all local IDs intact for replay.
  const next = {
    ...status, key, encryptedCredential: await encrypt(key, credential),
    clockOffset: nextClock(same ? state : null, status, clientMs),
    localSequence: same && pending.length ? state.localSequence : status.last_sequence,
    localHash: same && pending.length ? state.localHash : status.last_hash,
  };
  await save(database, next);
  return next;
}

function summary(state, entries) {
  return {
    code: state?.code,
    site: state?.site,
    evidenceMode: state?.evidence_mode,
    evidenceNotice: state?.evidence_notice,
    expires: state?.expires_ms,
    queued: entries.filter((entry) => !entry.quarantined).length,
    quarantined: entries.filter((entry) => entry.quarantined).length,
  };
}

export function enroll(credential) {
  return exclusive(async (database) => {
    const [state, entries] = await read(database);
    const enrolled = await establish(database, credential.trim(), state, entries);
    return summary(enrolled, entries);
  });
}

export function terminalStatus() {
  return exclusive(async (database) => summary(...await read(database)));
}

export function refreshTerminal() {
  return exclusive(async (database) => {
    const [state, entries] = await read(database);
    if (!state) return summary(state, entries);
    const updated = await establish(database, await decrypt(state.key, state.encryptedCredential), state, entries);
    return summary(updated, entries);
  });
}

export function queueScan(qr, direction, location, jpeg, localCapturedMs = Date.now()) {
  return exclusive(async (database) => {
    const [state, entries] = await read(database);
    if (!state) throw new Error('Enroll this terminal first.');
    if (entries.length >= 1000) {
      throw new Error('Terminal storage is full. Sync or archive scans before continuing.');
    }
    const event = {
      client_event_id: crypto.randomUUID(), generation: state.generation, sequence: state.localSequence + 1,
      captured_ms: localCapturedMs + state.clockOffset,
      latitude_e6: location ? Math.round(location.latitude * 1e6) : null,
      longitude_e6: location ? Math.round(location.longitude * 1e6) : null,
      accuracy_mm: location ? Math.round(location.accuracy * 1000) : null,
      direction, qr_payload: qr, jpeg, lease: state.lease, previous_hash: state.localHash,
    };
    event.event_hash = hex(await crypto.subtle.digest('SHA-256', text.encode(canonical(event))));
    const credential = await decrypt(state.key, state.encryptedCredential);
    const signingKey = await crypto.subtle.importKey('raw', text.encode(credential), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    event.device_mac = hex(await crypto.subtle.sign('HMAC', signingKey, text.encode(event.event_hash)));
    const record = { sequence: event.sequence, sealed: await encrypt(state.key, JSON.stringify(event)) };
    try {
      await save(database, { ...state, localSequence: event.sequence, localHash: event.event_hash }, record);
    } catch {
      throw new Error('The scan could not be saved to terminal storage. Contact your supervisor.');
    }
    return { eventId: event.client_event_id, leaseValid: clock(state) <= state.expires_ms };
  });
}

export function flush() {
  return exclusive(async (database) => {
    const [state, entries] = await read(database);
    if (!state) return [];
    const pending = entries.filter((entry) => !entry.quarantined);
    if (!pending.length) return [];
    const credential = await decrypt(state.key, state.encryptedCredential);
    const results = [];
    for (let offset = 0; offset < pending.length; offset += 20) {
      const current = pending.slice(offset, offset + 20);
      const events = await Promise.all(current.map(async (entry) => JSON.parse(await decrypt(state.key, entry.sealed))));
      const data = await api('/scans/offline-batches', credential, { events });
      const acknowledged = [];
      const quarantined = [];
      for (const [index, receipt] of data.receipts.entries()) {
        const event = events[index];
        if (!event || receipt.client_event_id !== event.client_event_id || receipt.event_hash !== event.event_hash ||
            (receipt.chain_advanced && receipt.sequence !== event.sequence) || !receipt.id) {
          throw new Error('The server receipt cannot be matched. The terminal has kept the pending scans.');
        }
        results.push(receipt);
        if (!receipt.chain_advanced) break;
        if (receipt.result === 'QUARANTINED') quarantined.push(current[index]);
        else acknowledged.push(event.sequence);
      }
      await save(database, state, null, acknowledged, quarantined);
      if (data.receipts.length !== events.length || !data.receipts.at(-1)?.chain_advanced) {
        throw new Error('Scan order could not be confirmed. Pending scans are still on this terminal.');
      }
    }
    return results;
  });
}

export function quarantineReceipts() {
  return exclusive(async (database) => {
    const [state, entries] = await read(database);
    const archived = entries.filter((entry) => entry.quarantined);
    const output = [];
    for (const entry of archived) {
      const event = JSON.parse(await decrypt(state.key, entry.sealed));
      output.push({ sequence: event.sequence, event_id: event.client_event_id,
        captured_at: new Date(event.captured_ms).toISOString(), event_hash: event.event_hash });
    }
    return output;
  });
}

export function clearQuarantine() {
  return exclusive(async (database) => {
    const [state, entries] = await read(database);
    if (state) await save(database, state, null, entries.filter((entry) => entry.quarantined).map((entry) => entry.sequence));
    return summary(state, entries.filter((entry) => !entry.quarantined));
  });
}
