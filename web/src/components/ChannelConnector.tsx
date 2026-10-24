import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api } from '../api';
import { errorMessage, fieldErrors } from '../lib/errors';
import { validateContact } from '../lib/validation';
import type { ChannelType, ChannelView, SendTestResult } from '../types';
import { Alert, Spinner } from './ui';
import { VerifyChannelDialog } from './VerifyChannelDialog';

const POLL_MS = 2000; // Section 10.2: the page checks every 2 seconds
const LINK_LIFETIME_MS = 10 * 60 * 1000;

/**
 * The "connect this channel" part, shared by sign-up (step 2) and the
 * Notifications section of the dashboard, so both behave the same.
 *
 *  - Email and Discord: type/paste the contact -> we send a 6-digit code -> code dialog
 *  - Telegram: "Open Telegram" (or send the /start command) -> we notice within 2 s (Change 1)
 */
export function ChannelConnector({
  type,
  defaultContact = '',
  onConnected,
  autoFocus = false,
}: {
  type: ChannelType;
  defaultContact?: string;
  onConnected: (channel: ChannelView) => void;
  autoFocus?: boolean;
}) {
  if (type === 'telegram') return <TelegramConnector onConnected={onConnected} />;
  return <CodeConnector type={type} defaultContact={defaultContact} onConnected={onConnected} autoFocus={autoFocus} />;
}

function CodeConnector({
  type,
  defaultContact,
  onConnected,
  autoFocus,
}: {
  type: 'email' | 'discord';
  defaultContact: string;
  onConnected: (channel: ChannelView) => void;
  autoFocus: boolean;
}) {
  const [contact, setContact] = useState(defaultContact);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{ channel: ChannelView; test: SendTestResult } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const err = validateContact(type, contact);
    if (err) return setError(err);
    setBusy(true);
    setError(null);
    try {
      const channel = await api.addChannel(type, contact.trim());
      const test = await api.sendTestCode(channel.channelId);
      setPending({ channel, test });
    } catch (e2) {
      setError(fieldErrors(e2).contact ?? errorMessage(e2));
    } finally {
      setBusy(false);
    }
  }

  const id = `contact-${type}`;
  return (
    <>
      <form onSubmit={submit} className="space-y-2" noValidate>
        <label htmlFor={id} className="label">
          {type === 'email' ? 'Email address' : 'Discord webhook URL'}
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            id={id}
            className={`input ${error ? 'input-error' : ''}`}
            type={type === 'email' ? 'email' : 'url'}
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder={type === 'email' ? 'you@example.com' : 'https://discord.com/api/webhooks/…'}
            autoFocus={autoFocus}
            aria-invalid={!!error}
          />
          <button type="submit" className="btn-primary shrink-0" disabled={busy}>
            {busy && <Spinner />} Send test message
          </button>
        </div>
        {error ? (
          <p className="text-sm text-rose-600">{error}</p>
        ) : (
          <p className="text-xs text-slate-500">
            {type === 'email' ? (
              'We will email you a 6-digit code to confirm the address.'
            ) : (
              <>
                In Discord: Server Settings → Integrations → Webhooks → New Webhook → Copy Webhook URL. We post a
                6-digit code to that channel.
              </>
            )}
          </p>
        )}
      </form>

      {pending && (
        <VerifyChannelDialog
          channel={pending.channel}
          initialDemoCode={pending.test.demoCode}
          onClose={() => setPending(null)}
          onVerified={(ch) => {
            setPending(null);
            onConnected(ch);
          }}
        />
      )}
    </>
  );
}

function TelegramConnector({ onConnected }: { onConnected: (channel: ChannelView) => void }) {
  const [state, setState] = useState<'idle' | 'starting' | 'ready' | 'waiting' | 'expired'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | null>(null);
  const startedAt = useRef(0);

  // Live mode gets the link as soon as this shows up, so "Open Telegram" can be a
  // real link: browsers only open another app straight from a click, not after
  // the page has waited for the server. (The mock fakes "Start" once a link is
  // requested, so it still asks on click.)
  useEffect(() => {
    if (api.mode === 'live') void getLink();
    return () => stopPolling();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function stopPolling() {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
  }

  async function getLink(): Promise<boolean> {
    setError(null);
    setCopied(false);
    setState('starting');
    try {
      const res = await api.startTelegramLink();
      setLink(res.url);
      setState('ready');
      startPolling();
      return true;
    } catch (e) {
      setError(errorMessage(e));
      setState('idle');
      return false;
    }
  }

  /** Checks every 2 seconds whether the bot has linked the chat, whichever way the user sent /start. */
  function startPolling() {
    startedAt.current = Date.now();
    stopPolling();
    timer.current = window.setInterval(async () => {
      if (Date.now() - startedAt.current > LINK_LIFETIME_MS) {
        stopPolling();
        setState('expired');
        return;
      }
      try {
        const channels = await api.getChannels();
        const tg = channels.find((c) => c.channelType === 'telegram' && c.isVerified);
        if (tg) {
          stopPolling();
          onConnected(tg);
        }
      } catch {
        /* keep waiting; a single failed check is not a problem */
      }
    }, POLL_MS);
  }

  async function openMock() {
    if (await getLink()) setState('waiting');
  }

  /** Backup: copy "/start <token>" so the user can paste it into the bot chat. */
  async function copyCommand() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(startCommand(link));
      setCopied(true);
    } catch {
      setError('Could not copy. Select the command and copy it by hand.');
    }
  }

  const live = api.mode === 'live';
  const hasLink = link && (state === 'ready' || state === 'waiting');
  return (
    <div className="space-y-3">
      {state === 'expired' ? (
        <>
          <button type="button" className="btn-primary" onClick={() => (live ? getLink() : openMock())}>
            Get a new link
          </button>
          <p className="text-xs text-slate-500">The link expired after 10 minutes.</p>
        </>
      ) : hasLink && live ? (
        // A real link, so the click itself opens the Telegram app (tg:// keeps the start token).
        <a href={toTgLink(link)} className="btn-primary inline-flex" onClick={() => setState('waiting')}>
          Open Telegram
        </a>
      ) : (
        <button type="button" className="btn-primary" onClick={openMock} disabled={state === 'starting' || (live && !link)}>
          {state === 'starting' && <Spinner />} Open Telegram
        </button>
      )}

      {state === 'waiting' ? (
        <p className="flex items-center gap-2 text-sm font-medium text-sky-900">
          <Spinner /> Waiting for you to press <strong>Start</strong> in Telegram…
          {!live && <span className="font-normal text-sky-800">(demo mode: we will pretend you did in a few seconds)</span>}
        </p>
      ) : (
        state !== 'expired' && (
          <p className="text-xs text-slate-500">Opens a chat with our bot. Press Start there and this page updates by itself. No code to type.</p>
        )
      )}

      {hasLink && live && (
        <div className="space-y-2 rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
          <p>
            Telegram didn't open? Open <strong>@{botName(link)}</strong> in Telegram (or{' '}
            <a href={link} target="_blank" rel="noreferrer" className="font-semibold underline">in the browser</a>) and send this message:
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <code className="break-all rounded bg-white px-2 py-1 font-mono text-[11px] text-slate-800">{startCommand(link)}</code>
            <button type="button" className="btn-secondary px-2.5 py-1 text-xs" onClick={copyCommand}>
              {copied ? '✓ Copied' : 'Copy'}
            </button>
          </div>
          <p className="text-sky-800">This page notices within 2 seconds either way.</p>
        </div>
      )}
      {error && <Alert>{error}</Alert>}
    </div>
  );
}

/** https://t.me/<bot>?start=<token>  ->  tg://resolve?domain=<bot>&start=<token> */
function toTgLink(url: string): string {
  const u = new URL(url);
  return `tg://resolve?domain=${botName(url)}&start=${u.searchParams.get('start') ?? ''}`;
}

function botName(url: string): string {
  return new URL(url).pathname.replace(/^\//, '');
}

function startCommand(url: string): string {
  return `/start ${new URL(url).searchParams.get('start') ?? ''}`;
}