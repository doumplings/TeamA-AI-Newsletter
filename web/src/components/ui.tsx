import type { ReactNode } from 'react';
import type { ChannelType, DeliveryStatus, ImportanceLevel } from '../types';

export function Spinner({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
      <path d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ className = '' }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-bold tracking-tight text-slate-900 ${className}`}>
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-indigo-600 text-white">
        <svg viewBox="0 0 32 32" className="h-5 w-5" fill="none">
          <path d="M8 23V9l8 8 8-8v14" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      AI Newsletter
    </span>
  );
}

export function Field({ label, error, hint, children, htmlFor }: { label: string; error?: string; hint?: ReactNode; children: ReactNode; htmlFor: string }) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>{label}</label>
      {children}
      {error ? <p className="mt-1.5 text-sm text-rose-600">{error}</p> : hint ? <p className="mt-1.5 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function Alert({ tone = 'error', children }: { tone?: 'error' | 'info' | 'success'; children: ReactNode }) {
  const cls = {
    error: 'border-rose-200 bg-rose-50 text-rose-700',
    info: 'border-sky-200 bg-sky-50 text-sky-800',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  }[tone];
  return <div role={tone === 'error' ? 'alert' : 'status'} className={`rounded-lg border px-3 py-2.5 text-sm ${cls}`}>{children}</div>;
}

const LEVEL_STYLE: Record<ImportanceLevel, string> = {
  high: 'bg-rose-100 text-rose-700',
  medium: 'bg-amber-100 text-amber-800',
  low: 'bg-slate-100 text-slate-600',
};

export function LevelBadge({ level }: { level: ImportanceLevel }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${LEVEL_STYLE[level]}`}>{level}</span>;
}

const STATUS_STYLE: Record<DeliveryStatus, [string, string]> = {
  sent: ['Sent', 'bg-emerald-100 text-emerald-700'],
  queued: ['Queued', 'bg-sky-100 text-sky-700'],
  failed: ['Retrying', 'bg-amber-100 text-amber-800'],
  permanent_failure: ['Failed', 'bg-rose-100 text-rose-700'],
};

export function StatusBadge({ status }: { status: DeliveryStatus }) {
  const [label, cls] = STATUS_STYLE[status];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${cls}`}>{label}</span>;
}

export function ChannelIcon({ type, className = 'h-10 w-10' }: { type: ChannelType; className?: string }) {
  if (type === 'telegram') {
    return (
      <span className={`grid shrink-0 place-items-center rounded-lg bg-sky-100 text-sky-600 ${className}`}>
        <svg viewBox="0 0 24 24" className="h-1/2 w-1/2" fill="currentColor" aria-hidden>
          <path d="M21.9 4.3 18.7 19.5c-.2 1-.9 1.3-1.8.8l-4.9-3.6-2.4 2.3c-.3.3-.5.5-1 .5l.3-5 9.2-8.3c.4-.4-.1-.6-.6-.2L6.2 13.2l-4.9-1.5c-1-.3-1.1-1 .2-1.6l19.1-7.4c.9-.3 1.6.2 1.3 1.6Z" />
        </svg>
      </span>
    );
  }
  if (type === 'discord') {
    return (
      <span className={`grid shrink-0 place-items-center rounded-lg bg-indigo-100 text-indigo-600 ${className}`}>
        <svg viewBox="0 0 24 24" className="h-1/2 w-1/2" fill="currentColor" aria-hidden>
          <path d="M19.6 5.3A17 17 0 0 0 15.4 4l-.5 1a15.6 15.6 0 0 0-5.8 0l-.5-1a17 17 0 0 0-4.2 1.3C1.7 9.3 1 13.2 1.3 17a17 17 0 0 0 5.2 2.6l1.1-1.8c-.6-.2-1.2-.5-1.7-.9l.4-.3a12.2 12.2 0 0 0 11.4 0l.4.3c-.5.4-1.1.7-1.7.9l1.1 1.8a17 17 0 0 0 5.2-2.6c.4-4.4-.7-8.3-3.1-11.7ZM8.5 14.7c-1 0-1.9-1-1.9-2.1s.8-2.1 1.9-2.1 1.9 1 1.9 2.1-.8 2.1-1.9 2.1Zm7 0c-1 0-1.9-1-1.9-2.1s.8-2.1 1.9-2.1 1.9 1 1.9 2.1-.8 2.1-1.9 2.1Z" />
        </svg>
      </span>
    );
  }
  return (
    <span className={`grid shrink-0 place-items-center rounded-lg bg-emerald-100 text-emerald-600 ${className}`}>
      <svg viewBox="0 0 24 24" className="h-1/2 w-1/2" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="m3 7 9 6 9-6" />
      </svg>
    </span>
  );
}

export function DemoBanner({ mode }: { mode: 'mock' | 'live' }) {
  if (mode === 'live') return null;
  return (
    <div className="bg-amber-50 px-4 py-1.5 text-center text-xs font-medium text-amber-800">
      Demo mode: fake data, nothing is really sent. Set VITE_API_MODE=live to use the server.
    </div>
  );
}

export function PageSpinner() {
  return (
    <div className="grid place-items-center py-24 text-slate-400">
      <Spinner className="h-6 w-6" />
    </div>
  );
}
