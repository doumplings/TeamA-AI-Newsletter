import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { Alert, PageSpinner, Spinner } from '../components/ui';
import { errorMessage } from '../lib/errors';
import type { CycleType, PipelineStatusView } from '../types';

const REFRESH_MS = 10_000;

const CYCLE_STYLE: Record<CycleType, string> = {
  scrape: 'bg-sky-100 text-sky-700',
  classify: 'bg-violet-100 text-violet-700',
  dispatch: 'bg-emerald-100 text-emerald-700',
};

/** Pipeline status (admin only): counts at each stage and the latest collector cycles. Refreshes itself. */
export default function AdminPipelinePage() {
  const [data, setData] = useState<PipelineStatusView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setData(await api.adminPipelineStatus());
      setUpdatedAt(new Date());
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }, []);

  // Load once, then every 10 seconds while the page is open.
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  if (loading) return <PageSpinner />;
  if (!data) return <Alert>{error ?? 'Could not load the pipeline status.'}</Alert>;

  const c = data.counts;
  const groups: { title: string; tiles: [string, number][] }[] = [
    { title: 'Collection', tiles: [['Sources', c.sources], ['Active sources', c.activeSources], ['News items', c.newsItems], ['Duplicates', c.duplicates]] },
    { title: 'Classification', tiles: [['Unclassified', c.unclassified], ['High', c.high], ['Medium', c.medium], ['Low', c.low]] },
    { title: 'Delivery', tiles: [['Waiting to send', c.undispatched], ['Queued', c.deliveriesQueued], ['Sent', c.deliveriesSent], ['Retrying', c.deliveriesFailed], ['Failed for good', c.deliveriesPermanentFailure]] },
    { title: 'Subscribers', tiles: [['Subscribers', c.subscribers], ['Verified channels', c.verifiedChannels]] },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Pipeline</h1>
          <p className="text-sm text-slate-600">What the collector, classifier and sender are doing right now.</p>
        </div>
        <div className="flex items-center gap-3">
          {updatedAt && <span className="text-xs text-slate-500">Updated {updatedAt.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>}
          <button className="btn-secondary" onClick={refresh} disabled={refreshing}>{refreshing && <Spinner />} Refresh</button>
        </div>
      </div>

      {error && <Alert>{error}</Alert>}

      {groups.map((g) => (
        <section key={g.title}>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">{g.title}</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {g.tiles.map(([label, value]) => (
              <div key={label} className="card p-5">
                <p className="text-sm text-slate-500">{label}</p>
                <p className="mt-2 text-2xl font-bold">{value.toLocaleString()}</p>
              </div>
            ))}
          </div>
        </section>
      ))}

      <section className="card overflow-x-auto">
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 className="font-semibold">Recent cycles</h2>
          <p className="text-sm text-slate-600">The latest runs, newest first.</p>
        </div>
        {data.runs.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-slate-500">No cycles have run yet.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-5 py-3 font-semibold">Cycle</th>
                <th className="px-3 py-3 font-semibold">Started</th>
                <th className="px-3 py-3 font-semibold">Duration</th>
                <th className="px-3 py-3 text-right font-semibold">Items</th>
                <th className="px-3 py-3 text-right font-semibold">Failures</th>
                <th className="px-5 py-3 font-semibold">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.runs.map((r) => (
                <tr key={r.runId} className="hover:bg-slate-50">
                  <td className="px-5 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${CYCLE_STYLE[r.cycleType]}`}>{r.cycleType}</span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 text-slate-500">
                    {new Date(r.startedAt).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit' })}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 text-slate-500">{duration(r.startedAt, r.finishedAt)}</td>
                  <td className="px-3 py-3 text-right">{r.itemsProcessed}</td>
                  <td className={`px-3 py-3 text-right ${r.failures > 0 ? 'font-semibold text-rose-600' : 'text-slate-500'}`}>{r.failures}</td>
                  <td className="max-w-xs truncate px-5 py-3 font-mono text-xs text-slate-500" title={r.notes ?? undefined}>{r.notes ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function duration(startedAt: string, finishedAt: string | null) {
  if (!finishedAt) return 'Not finished';
  const s = Math.max(0, Math.round((new Date(finishedAt).getTime() - new Date(startedAt).getTime()) / 1000));
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
}
