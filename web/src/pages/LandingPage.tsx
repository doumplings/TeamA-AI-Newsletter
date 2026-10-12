import { Link } from 'react-router-dom';
import { ChannelIcon, LevelBadge, Logo } from '../components/ui';
import { useAuth } from '../context/AuthContext';

/** Public landing page (UC-1, UI-1, UI-2). */
export default function LandingPage() {
  const { account } = useAuth();

  return (
    <div className="min-h-screen bg-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <Logo />
        <nav className="flex items-center gap-2">
          {account ? (
            <Link to="/dashboard" className="btn-primary">Go to dashboard</Link>
          ) : (
            <>
              <Link to="/login" className="btn-ghost">Log in</Link>
              <Link to="/signup" className="btn-primary">Get started</Link>
            </>
          )}
        </nav>
      </header>

      <main>
        {/* Hero */}
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-12 sm:px-6 lg:grid-cols-2 lg:pt-20">
          <div>
            <p className="mb-4 inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">
              Free · No spam · Only what matters
            </p>
            <h1 className="text-4xl font-bold leading-tight tracking-tight text-slate-900 sm:text-5xl">
              Important AI news, sent to the app you already use.
            </h1>
            <p className="mt-5 max-w-xl text-lg text-slate-600">
              We watch the blogs and news feeds of the major AI companies, score every story by how important it is, and send only the
              ones you care about to Telegram, Discord, or email.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link to="/signup" className="btn-primary px-6 py-3 text-base">Get started</Link>
              <Link to="/login" className="btn-secondary px-6 py-3 text-base">I already have an account</Link>
            </div>
            <div className="mt-8 flex items-center gap-3 text-sm text-slate-500">
              <ChannelIcon type="telegram" className="h-8 w-8" />
              <ChannelIcon type="discord" className="h-8 w-8" />
              <ChannelIcon type="email" className="h-8 w-8" />
              <span>Works with Telegram, Discord and email</span>
            </div>
          </div>

          {/* Preview card: what a notification looks like */}
          <div className="relative">
            <div className="absolute -inset-4 -z-10 rounded-3xl bg-gradient-to-br from-indigo-100 via-sky-50 to-white" />
            <div className="card space-y-3 p-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Today</p>
              {[
                { t: 'New model released for developers', s: 'Official AI company blog', l: 'high' as const, ago: '12 min ago' },
                { t: 'Older API versions to be retired next quarter', s: 'Official AI company blog', l: 'high' as const, ago: '2 h ago' },
                { t: 'AI startup raises $400M in new funding', s: 'Technology news site', l: 'medium' as const, ago: '5 h ago' },
              ].map((n) => (
                <div key={n.t} className="flex items-start gap-3 rounded-lg border border-slate-100 p-3">
                  <ChannelIcon type="telegram" className="h-9 w-9" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <LevelBadge level={n.l} />
                      <span className="text-xs text-slate-400">{n.ago}</span>
                    </div>
                    <p className="mt-1 text-sm font-semibold text-slate-900">{n.t}</p>
                    <p className="text-xs text-slate-500">{n.s}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* How it works */}
        <section className="border-t border-slate-100 bg-slate-50 py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="text-2xl font-bold tracking-tight">How it works</h2>
            <div className="mt-8 grid gap-6 md:grid-cols-3">
              {[
                { n: '1', t: 'Create an account', d: 'Just an email and a password. Takes under a minute.' },
                { n: '2', t: 'Connect a channel', d: 'Press Start in Telegram, or confirm a 6-digit code for Discord or email.' },
                { n: '3', t: 'Pick your level', d: 'High only, Medium and up, or Everything. Change it any time per channel.' },
              ].map((s) => (
                <div key={s.n} className="card p-6">
                  <span className="grid h-9 w-9 place-items-center rounded-full bg-indigo-600 text-sm font-bold text-white">{s.n}</span>
                  <h3 className="mt-4 font-semibold">{s.t}</h3>
                  <p className="mt-1 text-sm text-slate-600">{s.d}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Importance levels */}
        <section className="py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="text-2xl font-bold tracking-tight">You decide how much you hear</h2>
            <p className="mt-2 max-w-2xl text-slate-600">
              Every story gets an importance score from its source, what it is about (new models, shutdowns, pricing, funding, regulation),
              and how many sites report it.
            </p>
            <div className="mt-8 grid gap-4 md:grid-cols-3">
              <div className="card p-5"><LevelBadge level="high" /><p className="mt-3 text-sm text-slate-600">Model launches, shutdowns and breaking API changes. A few a week.</p></div>
              <div className="card p-5"><LevelBadge level="medium" /><p className="mt-3 text-sm text-slate-600">Also pricing changes, big funding rounds and new regulation.</p></div>
              <div className="card p-5"><LevelBadge level="low" /><p className="mt-3 text-sm text-slate-600">Everything else: research posts, tutorials and community threads.</p></div>
            </div>
            <div className="mt-10">
              <Link to="/signup" className="btn-primary px-6 py-3 text-base">Get started</Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-slate-100 py-8 text-center text-sm text-slate-500">
        AI Newsletter · CSCI 441 Team A project
      </footer>
    </div>
  );
}
