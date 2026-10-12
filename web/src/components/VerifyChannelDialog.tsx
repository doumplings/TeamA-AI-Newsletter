import { useEffect, useState } from 'react';
import { api } from '../api';
import { errorMessage } from '../lib/errors';
import type { ChannelView } from '../types';
import { CHANNEL_LABEL } from '../types';
import { CodeInput } from './CodeInput';
import { Alert, ChannelIcon, Spinner } from './ui';

/**
 * Dialog that waits for the 6-digit code (UC-5, VerifyChannelDialog in Section 8).
 * The code checks itself after the 6th digit. Wrong codes show how many tries
 * are left (3). After 3 wrong tries, a new code has to be sent.
 */
export function VerifyChannelDialog({
  channel,
  initialDemoCode,
  onVerified,
  onClose,
}: {
  channel: ChannelView;
  initialDemoCode?: string;
  onVerified: (channel: ChannelView) => void;
  onClose: () => void;
}) {
  const [attemptsLeft, setAttemptsLeft] = useState(3);
  const [checking, setChecking] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const [demoCode, setDemoCode] = useState(initialDemoCode);

  // Close with Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function submitCode(code: string) {
    setChecking(true);
    setError(null);
    try {
      const res = await api.confirmCode(channel.channelId, code);
      if (res.ok && res.channel) {
        onVerified(res.channel);
        return;
      }
      setAttemptsLeft(res.attemptsLeft);
      setError(
        res.attemptsLeft > 0
          ? `That code is not right. ${res.attemptsLeft} ${res.attemptsLeft === 1 ? 'try' : 'tries'} left.`
          : 'Too many wrong codes. Send a new code to try again.',
      );
      setInputKey((k) => k + 1);
    } catch (e) {
      setError(errorMessage(e));
      setInputKey((k) => k + 1);
    } finally {
      setChecking(false);
    }
  }

  async function resend() {
    setResending(true);
    setError(null);
    try {
      const res = await api.sendTestCode(channel.channelId);
      setDemoCode(res.demoCode);
      setAttemptsLeft(3);
      setInputKey((k) => k + 1);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setResending(false);
    }
  }

  const where = channel.channelType === 'email' ? 'inbox' : `${CHANNEL_LABEL[channel.channelType]} channel`;

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-slate-900/40 p-4" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="verify-title"
        className="card w-full max-w-md p-6"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <ChannelIcon type={channel.channelType} />
          <div>
            <h2 id="verify-title" className="text-lg font-semibold">Enter the code we sent</h2>
            <p className="text-sm text-slate-600">
              Check your {where} ({channel.maskedContact}) for a 6-digit code.
            </p>
          </div>
        </div>

        {demoCode && (
          <div className="mt-4">
            <Alert tone="info">
              Demo mode: your code is <strong className="font-mono tracking-widest">{demoCode}</strong>
            </Alert>
          </div>
        )}

        <div className="mt-6">
          <CodeInput key={inputKey} onComplete={submitCode} disabled={checking || attemptsLeft <= 0} />
        </div>

        <div className="mt-4 min-h-[2.5rem]" aria-live="polite">
          {checking && (
            <p className="flex items-center justify-center gap-2 text-sm text-slate-600">
              <Spinner /> Checking code…
            </p>
          )}
          {!checking && error && <Alert>{error}</Alert>}
        </div>

        <div className="mt-2 flex items-center justify-between">
          <button type="button" className="btn-ghost px-2" onClick={resend} disabled={resending}>
            {resending ? <Spinner /> : null} Send a new code
          </button>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
        </div>
        <p className="mt-3 text-center text-xs text-slate-500">The code is valid for 10 minutes.</p>
      </div>
    </div>
  );
}
