import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Logo } from './ui';

export function AuthLayout({ title, subtitle, children, footer, step }: { title: string; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode; step?: string }) {
  return (
    <div className="flex min-h-screen flex-col items-center px-4 py-10">
      <Link to="/" aria-label="Home"><Logo /></Link>
      <div className="card mt-8 w-full max-w-md p-6 sm:p-8">
        {step && <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-indigo-600">{step}</p>}
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </div>
      {footer && <div className="mt-6 text-sm text-slate-600">{footer}</div>}
    </div>
  );
}
