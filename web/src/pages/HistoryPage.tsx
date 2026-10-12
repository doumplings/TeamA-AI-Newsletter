import { useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { Alert, ChannelIcon, LevelBadge, PageSpinner, StatusBadge } from '../components/ui';
import { useLoad } from '../lib/useLoad';
import { CHANNEL_LABEL } from '../types';

/** Notification history, newest first, one page at a time (UC-8, HistoryPage in Section 8). */
export default function HistoryPage() {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const { data, error, loading } = useLoad(() => api.getHistory(page), [page]);

  const goTo = (p: number) => setParams(p === 1 ? {} : { page: String(p) });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">History</h1>
        <p className="text-sm text-slate-600">Every news item we sent you, newest first.</p>
      </div>

      {loading ? (
        <PageSpinner />
      ) : error || !data ? (
        <Alert>{error ?? 'Could not load your history.'}</Alert>
      ) : data.items.length === 0 ? (
        <div className="card px-6 py-16 text-center">
          <p className="font-semibold">No notifications yet</p>
          <p className="mt-1 text-sm text-slate-500">When we send you news, it will be listed here.</p>
        </div>
      ) : (
        <>
          <div className="card overflow-hidden">
            {/* Table on larger screens */}
            <table className="hidden w-full text-left text-sm md:table">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-semibold">News</th>
                  <th className="px-3 py-3 font-semibold">Level</th>
                  <th className="px-3 py-3 font-semibold">Channel</th>
                  <th className="px-3 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 text-right font-semibold">Sent</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((d) => (
                  <tr key={d.deliveryId} className="hover:bg-slate-50">
                    <td className="max-w-md px-5 py-3">
                      <a href={d.link} target="_blank" rel="noreferrer" className="font-medium text-slate-900 hover:text-indigo-700 hover:underline">{d.title}</a>
                      <p className="text-xs text-slate-500">{d.sourceName}</p>
                    </td>
                    <td className="px-3 py-3"><LevelBadge level={d.importanceLevel} /></td>
                    <td className="px-3 py-3">
                      <span className="inline-flex items-center gap-2"><ChannelIcon type={d.channelType} className="h-6 w-6" />{CHANNEL_LABEL[d.channelType]}</span>
                    </td>
                    <td className="px-3 py-3"><StatusBadge status={d.status} /></td>
                    <td className="whitespace-nowrap px-5 py-3 text-right text-slate-500">{formatDate(d.sentAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Cards on phones */}
            <ul className="divide-y divide-slate-100 md:hidden">
              {data.items.map((d) => (
                <li key={d.deliveryId} className="flex gap-3 p-4">
                  <ChannelIcon type={d.channelType} className="h-8 w-8" />
                  <div className="min-w-0 flex-1">
                    <a href={d.link} target="_blank" rel="noreferrer" className="text-sm font-medium hover:underline">{d.title}</a>
                    <p className="text-xs text-slate-500">{d.sourceName} · {formatDate(d.sentAt)}</p>
                    <div className="mt-1.5 flex gap-2"><LevelBadge level={d.importanceLevel} /><StatusBadge status={d.status} /></div>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <nav className="flex items-center justify-between" aria-label="Pages">
            <button className="btn-secondary" onClick={() => goTo(data.page - 1)} disabled={data.page <= 1}>← Newer</button>
            <span className="text-sm text-slate-600">Page {data.page} of {data.totalPages}</span>
            <button className="btn-secondary" onClick={() => goTo(data.page + 1)} disabled={data.page >= data.totalPages}>Older →</button>
          </nav>
        </>
      )}
    </div>
  );
}

function formatDate(iso: string | null) {
  if (!iso) return 'Waiting';
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}
