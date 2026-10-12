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
 *  - Telegram: "Open Telegram" -> user presses Start -> we notice within 2 s (Change 1)
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
  const [state, setState] = useState<'idle' | 'starting' | 'waiting' | 'expired'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | null>(null);
  const startedAt = useRef(0);

  useEffect(() => () => stopPolling(), []);

  function stopPolling() {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
  }

  async function openTelegram() {
    setError(null);
    setCopied(false);
    setState('starting');
    try {
      const res = await api.startTelegramLink();
      setLink(res.url);
      if (api.mode === 'live') {
        // Desktop Telegram apps often drop the ?start= token when opened through an
        // https://t.me link. The tg:// form goes straight to the installed app and keeps it.
        window.location.href = toTgLink(res.url);
      }
      setState('waiting');
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
    } catch (e) {
      setError(errorMessage(e));
      setState('idle');
    }
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

  return (
    <div className="space-y-3">
      {state === 'waiting' ? (
        <div className="rounded-lg border border-sky-200 bg-sky-50 p-4">
          <p className="flex items-center gap-2 text-sm font-medium text-sky-900">
            <Spinner /> Waiting for you to press <strong>Start</strong> in Telegram…
          </p>
          <p className="mt-2 text-xs text-sky-800">
            {api.mode === 'mock'
              ? 'Demo mode: we will pretend you pressed Start in a few seconds.'
              : 'On a computer without the Telegram app, Telegram may ask you to sign in first. This page keeps waiting.'}
          </p>
          {link && api.mode === 'live' && (
            <div className="mt-3 space-y-2 border-t border-sky-200 pt-3 text-xs text-sky-900">
              <p>
                Telegram opened but nothing happened?{' '}
                <a href={link} target="_blank" rel="noreferrer" className="font-semibold underline">Open it in the browser</a>, or send
                this message to <strong>@{botName(link)}</strong>:
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <code className="break-all rounded bg-white px-2 py-1 font-mono text-[11px] text-slate-800">{startCommand(link)}</code>
                <button type="button" className="btn-secondary px-2.5 py-1 text-xs" onClick={copyCommand}>
                  {copied ? '✓ Copied' : 'Copy'}
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <>
          <button type="button" className="btn-primary" onClick={openTelegram} disabled={state === 'starting'}>
            {state === 'starting' && <Spinner />} Open Telegram
          </button>
          <p className="text-xs text-slate-500">
            {state === 'expired'
              ? 'The link expired after 10 minutes. Click again for a new one.'
              : 'Opens a chat with our bot. Press Start there and this page updates by itself. No code to type.'}
          </p>
        </>
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