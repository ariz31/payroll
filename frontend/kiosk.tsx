import type { IScannerControls } from '@zxing/browser';
import { ArrowLeft, Camera, CheckCircle2, CircleAlert, Clock3, MapPin, ScanLine, Volume2, VolumeX, Wifi, WifiOff } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ErrorNote, saveLocal } from './common';
import { clearQuarantine, enroll, flush, NetworkError, quarantineReceipts, queueScan, refreshTerminal,
  terminalStatus, type Receipt, type TerminalStatus } from './outbox.mjs';

type Direction = 'auto' | 'in' | 'out';
type Feedback = { tone: 'ok' | 'wait' | 'error'; title: string; detail?: string };

const results: Record<Receipt['result'], Feedback> = {
  ACCEPTED_IN: { tone: 'ok', title: 'Clock-In Recorded' },
  ACCEPTED_OUT: { tone: 'ok', title: 'Clock-Out Recorded' },
  IGNORED_DEBOUNCE: { tone: 'wait', title: 'Duplicate Tap Ignored' },
  REJECTED: { tone: 'error', title: 'Scan rejected', detail: 'Check the badge and terminal location or contact the supervisor.' },
  QUARANTINED: { tone: 'error', title: 'Needs supervisor review', detail: 'The scan is in the audit ledger and needs reconciliation.' },
};

function locationClaim(): Promise<{ coords: GeolocationCoordinates | null; message: string }> {
  if (!navigator.geolocation) return Promise.resolve({ coords: null, message: 'Geolocation is unavailable.' });
  return new Promise((resolve) => navigator.geolocation.getCurrentPosition(
    (position) => resolve({ coords: position.coords, message: 'Terminal location available.' }),
    (error) => resolve({ coords: null, message: error.code === 1 ? 'Allow location access for geofencing.' : 'Terminal GPS is unavailable.' }),
    { enableHighAccuracy: true, timeout: 4000, maximumAge: 120000 },
  ));
}

function capture(video: HTMLVideoElement | null) {
  if (!video?.videoWidth || !video.videoHeight) return '';
  const scale = Math.min(1, 360 / video.videoWidth, 270 / video.videoHeight);
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  const context = canvas.getContext('2d');
  if (!context) return '';
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  let encoded = '';
  for (const quality of [0.58, 0.40, 0.26]) {
    encoded = canvas.toDataURL('image/jpeg', quality).split(',')[1] || '';
    if (encoded.length <= 20500) break;
  }
  return encoded.length <= 88000 ? encoded : '';
}

export function Kiosk() {
  const [terminal, setTerminal] = useState<TerminalStatus>({ queued: 0, quarantined: 0 });
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState<Feedback>({ tone: 'wait', title: 'Ready for a badge' });
  const [online, setOnline] = useState(navigator.onLine);
  const [sound, setSound] = useState(false);
  const [camera, setCamera] = useState(false);
  const [busy, setBusy] = useState(false);
  const [direction, setDirection] = useState<Direction>('auto');
  const [claim, setClaim] = useState<{ coords: GeolocationCoordinates | null; message: string }>({ coords: null, message: 'Location is used to validate this terminal.' });
  const [archived, setArchived] = useState(false);
  const [enrolling, setEnrolling] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const audio = useRef<AudioContext | null>(null);
  const pending = useRef(false);
  const syncAfterCapture = useRef(false);
  const current = useRef<(token: string) => Promise<void>>(async () => {});
  const lastRead = useRef({ token: '', timestamp: 0 });

  const refresh = useCallback(async () => { setTerminal(await terminalStatus()); }, []);
  const sync = useCallback(async (renew = false) => {
    try {
      const receipts = await flush();
      if (receipts.length) setFeedback(results[receipts[receipts.length - 1].result]);
      if (renew) setTerminal(await refreshTerminal());
      else await refresh();
      setOnline(true);
      setError('');
      return receipts;
    } catch (cause) {
      if (cause instanceof NetworkError) setOnline(false);
      else setError((cause as Error).message);
      await refresh().catch(() => undefined);
      return [];
    }
  }, [refresh]);

  useEffect(() => {
    void refresh().then(async () => { if (navigator.onLine) await sync(true); })
      .catch((cause: Error) => setError(cause.message));
    const onlineHandler = () => {
      if (pending.current) syncAfterCapture.current = true;
      else void sync(true);
    };
    const offlineHandler = () => setOnline(false);
    window.addEventListener('online', onlineHandler);
    window.addEventListener('offline', offlineHandler);
    const timer = window.setInterval(() => {
      if (!pending.current && navigator.onLine) void sync();
    }, 8000);
    const renewal = window.setInterval(() => { if (!pending.current && navigator.onLine) void sync(true); }, 60000);
    return () => {
      window.clearInterval(timer);
      window.clearInterval(renewal);
      window.removeEventListener('online', onlineHandler);
      window.removeEventListener('offline', offlineHandler);
    };
  }, [refresh, sync]);

  useEffect(() => {
    let live = true;
    const audioContext = audio.current;
    let controls: IScannerControls | undefined;
    let stream: MediaStream | undefined;
    if (camera && terminal.code && video.current) {
      const element = video.current;
      import('@zxing/browser').then(async ({ BrowserQRCodeReader }) => {
          const reader = new BrowserQRCodeReader();
          const source = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: 'environment' }, width: { ideal: 640 } }, audio: false,
          });
          if (!live) { source.getTracks().forEach((track) => track.stop()); return; }
          stream = source;
          controls = await reader.decodeFromStream(source, element, (result) => {
            if (!live || !result) return;
            const token = result.getText();
            const time = Date.now();
            if (lastRead.current.token === token && time - lastRead.current.timestamp < 3500) return;
            if (pending.current) return;
            lastRead.current = { token, timestamp: time };
            void current.current(token);
          });
          if (!live) controls.stop();
        }).catch((cause: Error) => {
          if (live) setError(cause.name === 'NotAllowedError' ? 'Camera access was denied.' : 'The camera could not start. Use a USB scanner if site policy permits.');
        });
    }
    return () => {
      live = false;
      controls?.stop();
      stream?.getTracks().forEach((track) => track.stop());
      if (audioContext?.state === 'closed') audio.current = null;
    };
  }, [camera, terminal.code]);

  function play(tone: Feedback['tone']) {
    if (!sound || !audio.current) return;
    const context = audio.current;
    const oscillator = context.createOscillator();
    const volume = context.createGain();
    oscillator.frequency.value = tone === 'ok' ? 760 : tone === 'wait' ? 500 : 250;
    volume.gain.setValueAtTime(0.10, context.currentTime);
    volume.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.18);
    oscillator.connect(volume);
    volume.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.2);
  }

  async function scan(untrimmed: string) {
    const token = untrimmed.trim();
    if (!token || pending.current) return;
    const captured = Date.now();
    pending.current = true;
    setBusy(true); setError('');
    setFeedback({ tone: 'wait', title: 'Processing scan…' });
    let next: Feedback;
    try {
      const jpg = terminal.evidenceMode === 'off' ? '' : capture(video.current);
      const position = await locationClaim();
      setClaim(position);
      const saved = await queueScan(token, direction, position.coords, jpg, captured);
      const receipts = navigator.onLine ? await sync() : [];
      const receipt = receipts.find((item) => item.client_event_id === saved.eventId);
      next = receipt ? results[receipt.result] : {
        tone: 'wait', title: 'Offline Captured & Sealed',
        detail: saved.leaseValid ? 'Stored on this device. Acceptance is confirmed after synchronization.' :
          'The offline lease expired. A supervisor must reconcile this scan after synchronization.',
      };
    } catch (cause) {
      next = { tone: 'error', title: 'Capture failed', detail: (cause as Error).message };
    }
    setFeedback(next); play(next.tone); pending.current = false; setBusy(false);
    if (syncAfterCapture.current) {
      syncAfterCapture.current = false;
      void sync(true);
    }
    await refresh().catch(() => undefined);
    if (input.current) { input.current.value = ''; input.current.focus(); }
  }
  current.current = scan;

  async function saveEnrollment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setEnrolling(true); setError('');
    const form = event.currentTarget;
    const credential = String(new FormData(form).get('credential') || '');
    try {
      setTerminal(await enroll(credential));
      form.reset();
      setClaim(await locationClaim());
      setOnline(true);
      await navigator.storage?.persist?.();
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); setEnrolling(false); }
  }

  async function exportQuarantine() {
    const rows = await quarantineReceipts();
    saveLocal(`terminal-${terminal.code}-quarantine.json`, 'application/json', JSON.stringify(rows, null, 2));
    setArchived(true);
  }

  const FeedbackIcon = feedback.tone === 'ok' ? CheckCircle2 : feedback.tone === 'error' ? CircleAlert : Clock3;
  return <div className="kiosk-shell">
    <header className="kiosk-top"><a href="#overview" className="text-link"><ArrowLeft size={17} /> Back to workbench</a>
      <span className={`connection ${online ? 'connected' : ''}`}>{online ? <Wifi size={17} /> : <WifiOff size={17} />}{online ? 'Online' : 'Offline'}</span></header>
    <main className="kiosk">
      <HeadingKiosk terminal={terminal} />
      <ErrorNote text={error} />
      {!terminal.code ? <section className="panel">
        <div className="panel-body"><h2>Enroll this terminal</h2><p className="muted">Enter the credential from Administration on the device at the registered gate.</p>
          <form className="form-stack" onSubmit={saveEnrollment}><label>Terminal credential<input name="credential" type="password" required autoComplete="off" /></label>
            <button className="primary" disabled={busy}>{enrolling ? 'Enrolling…' : 'Enroll terminal'}</button></form></div>
      </section> : <>
        <div className={`scan-feedback ${feedback.tone}`} role="status" aria-live="polite"><FeedbackIcon size={28} /><div><strong>{feedback.title}</strong>{feedback.detail && <p>{feedback.detail}</p>}</div></div>
        {terminal.evidenceNotice && <p className="notice info"><Camera size={18} />{terminal.evidenceNotice}</p>}
        <section className="panel">
          <header className="panel-heading"><div><h2>Scan a badge</h2><p>Connect a USB scanner or start the camera.</p></div></header>
          <div className="panel-body form-stack">
            <div className="actions">
              <button className="secondary" onClick={() => { setError(''); setCamera(!camera); }}><Camera size={17} />{camera ? 'Stop camera' : 'Start camera'}</button>
              <button className="secondary" onClick={async () => {
                if (!sound) { audio.current ||= new AudioContext(); await audio.current.resume(); }
                setSound(!sound);
              }}>{sound ? <Volume2 size={17} /> : <VolumeX size={17} />}{sound ? 'Sound on' : 'Enable sound'}</button>
            </div>
            {camera && <video ref={video} className="kiosk-video" muted playsInline autoPlay aria-label="QR camera preview" />}
            <form className="filters" onSubmit={(event) => {
              event.preventDefault(); if (input.current) void scan(input.current.value);
            }}>
              <label>Action<select value={direction} onChange={(event) => setDirection(event.target.value as Direction)}>
                <option value="auto">Auto-detect</option><option value="in">Clock in</option><option value="out">Clock out</option></select></label>
              <label className="grow">Scanner input<input ref={input} name="badge" autoComplete="off" autoFocus required maxLength={256} placeholder="Scan or enter badge code" disabled={busy} /></label>
              <button className="primary" disabled={busy}>Submit scan</button>
            </form>
            <div className="inline-details"><span><MapPin size={16} />{claim.message}</span>
              <span>Queued <strong>{terminal.queued}</strong></span><span>Quarantined <strong>{terminal.quarantined}</strong></span></div>
            <div className="actions"><button className="secondary" disabled={busy} onClick={() => void sync(true)}>Sync now</button>
              {terminal.quarantined > 0 && <button className="secondary" onClick={() => void exportQuarantine().catch((cause: Error) => setError(cause.message))}>Download quarantine receipts</button>}
              {terminal.quarantined > 0 && archived && <button className="secondary" onClick={() => {
                if (window.confirm('Clear these retained local quarantine copies? Server audit records are retained.')) void clearQuarantine().then(setTerminal);
              }}>Clear local quarantine copies</button>}
            </div>
          </div>
        </section>
        <details className="panel kiosk-details"><summary>Update terminal enrollment</summary>
          <form className="form-stack" onSubmit={saveEnrollment}><label>Terminal credential<input name="credential" type="password" autoComplete="off" required /></label>
            <button className="secondary" disabled={busy}>Save credential</button></form></details>
      </>}
    </main>
  </div>;
}

function HeadingKiosk({ terminal }: { terminal: TerminalStatus }) {
  return <header className="kiosk-heading"><span className="brand-icon"><ScanLine /></span><div><h1>Terminal kiosk</h1>
    <p>{terminal.code ? `${terminal.site} · ${terminal.code}` : 'SiteGuard QR gate attendance'}</p></div></header>;
}
