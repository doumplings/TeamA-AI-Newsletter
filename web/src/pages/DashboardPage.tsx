import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { api } from '../api';
import { LevelPicker } from '../components/LevelPicker';
import { Alert, ChannelIcon, LevelBadge, PageSpinner, Spinner, StatusBadge } from '../components/ui';
import { useToast } from '../context/ToastContext';
import { errorMessage } from '../lib/errors';
import { timeAgo, useLoad } from '../lib/useLoad';
import type { ImportanceLevel, ProfileView, SourceView } from '../types';
import type { ChannelType } from '../types';
import { CHANNEL_LABEL, LEVEL_LABEL } from '../types';

/**
 * Dashboard overview (UC-6, UC-7, DashboardPage in Section 8):
 * default importance level, followed sources, and a quick look at recent news.
 */
export default function DashboardPage() {
  const toast = useToast();
  const location = useLocation();
  const justConnected = (location.state as { justConnected?: ChannelType } | null)?.justConnected;
  const { data, error, loading, setData } = useLoad(async () => {
    const [channels, profile, sources, history] = await Promise.all([
      api.getChannels(),
      api.getProfile(),
      api.getSources(),
      api.getHistory(1),
    ]);
    return { channels, profile, sources, history };
  });
  const [sending, setSending] = useState(false);

  async function sendSample() {
    setSending(true);
    try {
      const res = await api.sendSampleNews();
      if (res.delivered === 0 && res.failed === 0) toast('Connect a channel first.', 'error');
      else toast(`Sample news sent to ${res.delivered} channel${res.delivered === 1 ? '' : 's'}${res.failed ? `, ${res.failed} failed` : ''}.`, res.failed ? 'error' : 'success');
      const history = await api.getHistory(1);
      setData((d) => (d ? { ...d, history } : d));
    } catch (e) {
      toast(errorMessage(e), 'error');
    } finally {
      setSending(false);
    }
  }

  if (loading) return <PageSpinner />;
  if (error || !data) return <Alert>{error ?? 'Could not load your dashboard.'}</Alert>;

  const connected = data.channels.filter((c) => c.isVerified);
  const recent = data.history.items.slice(0, 5);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Overview</h1>
          <p className="text-sm text-slate-600">Your channels, importance level and sources at a glance.</p>
        </div>
        <button className="btn-secondary" onClick={sendSample} disabled={sending || connected.length === 0} title={connected.length === 0 ? 'Connect a channel first' : undefined}>
          {sending ? <Spinner /> : '📨'} Send me a sample news item
        </button>
      </div>

      {justConnected && (
        <Alert tone="success">
          You're all set! {CHANNEL_LABEL[justConnected]} is connected. Important AI news will arrive there.{' '}
          <Link to="/dashboard/notifications" className="font-semibold underline">Add another channel</Link>
        </Alert>
      )}

      {connected.length === 0 && (
        <div className="card flex flex-wrap items-center justify-between gap-4 border-indigo-200 bg-indigo-50 p-5">
          <div>
            <p className="font-semibold text-indigo-900">You have no channel connected yet</p>
            <p className="text-sm text-indigo-800">Connect Telegram, Discord or email to start receiving news.</p>
          </div>
          <Link to="/dashboard/notifications" className="btn-primary">Connect a channel</Link>
        </div>
      )}

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card p-5">
          <p className="text-sm text-slate-500">Connected channels</p>
          <div className="mt-2 flex items-center gap-2">
            <p className="text-2xl font-bold">{connected.length}</p>
            <div className="flex gap-1">
              {connected.map((c) => <ChannelIcon key={c.channelId} type={c.channelType} className="h-7 w-7" />)}
            </div>
          </div>
        </div>
        <div className="card p-5">
          <p className="text-sm text-slate-500">Default level</p>
          <p className="mt-2 text-2xl font-bold">{LEVEL_LABEL[data.profile.defaultThreshold]}</p>
        </div>
        <div className="card p-5">
          <p className="text-sm text-slate-500">Last notification</p>
          <p className="mt-2 text-2xl font-bold">{timeAgo(recent[0]?.sentAt ?? null)}</p>
        </div>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <DefaultLevelCard profile={data.profile} onSaved={(profile) => setData({ ...data, profile })} />
        <SourcesCard profile={data.profile} sources={data.sources} onSaved={(profile) => setData({ ...data, profile })} />
      </div>

      {/* Recent notifications */}
      <section className="card">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="font-semibold">Recent notifications</h2>
          <Link to="/dashboard/history" className="text-sm font-semibold text-indigo-600 hover:underline">View all</Link>
        </div>
        {recent.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-slate-500">Nothing yet. News you receive will show up here.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {recent.map((d) => (
              <li key={d.deliveryId} className="flex items-center gap-3 px-5 py-3">
                <ChannelIcon type={d.channelType} className="h-8 w-8" />
                <div className="min-w-0 flex-1">
                  <a href={d.link} target="_blank" rel="noreferrer" className="block truncate text-sm font-medium hover:text-indigo-700 hover:underline">{d.title}</a>
                  <p className="text-xs text-slate-500">{d.sourceName} · {timeAgo(d.sentAt)}</p>
                </div>
                <LevelBadge level={d.importanceLevel} />
                <span className="hidden sm:inline"><StatusBadge status={d.status} /></span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function DefaultLevelCard({ profile, onSaved }: { profile: ProfileView; onSaved: (p: ProfileView) => void }) {
  const toast = useToast();
  const [saving, setSaving] = useState(false);

  async function change(level: ImportanceLevel | null) {
    if (!level || level === profile.defaultThreshold) return;
    setSaving(true);
    try {
      onSaved(await api.setThreshold(level));
      toast(`Default level set to "${LEVEL_LABEL[level]}"`, 'success');
    } catch (e) {
      toast(errorMessage(e), 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card p-5">
      <h2 className="font-semibold">Default importance level</h2>
      <p className="mt-1 text-sm text-slate-600">Used by every channel that does not set its own level.</p>
      <div className="mt-4 flex items-center gap-3">
        <LevelPicker name="Default importance level" value={profile.defaultThreshold} onChange={change} disabled={saving} />
        {saving && <Spinner className="h-4 w-4 text-slate-400" />}
      </div>
    </section>
  );
}

function SourcesCard({ profile, sources, onSaved }: { profile: ProfileView; sources: SourceView[]; onSaved: (p: ProfileView) => void }) {
  const toast = useToast();
  const [picked, setPicked] = useState<Set<number>>(new Set(profile.followedSourceIds));
  const [saving, setSaving] = useState(false);

  useEffect(() => setPicked(new Set(profile.followedSourceIds)), [profile.followedSourceIds]);

  const dirty = useMemo(() => {
    const a = [...picked].sort().join(',');
    const b = [...profile.followedSourceIds].sort().join(',');
    return a !== b;
  }, [picked, profile.followedSourceIds]);

  function toggle(id: number) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function save() {
    setSaving(true);
    try {
      onSaved(await api.setFollowedSources([...picked]));
      toast('Sources saved', 'success');
    } catch (e) {
      toast(errorMessage(e), 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Followed sources</h2>
        <span className="text-xs text-slate-500">{picked.size} of {sources.length}</span>
      </div>
      <p className="mt-1 text-sm text-slate-600">You only get news from the sources you follow.</p>
      <ul className="mt-4 grid gap-2 sm:grid-cols-2">
        {sources.map((s) => (
          <li key={s.sourceId}>
            <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50">
              <input type="checkbox" className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" checked={picked.has(s.sourceId)} onChange={() => toggle(s.sourceId)} />
              <span className="truncate">{s.name}</span>
            </label>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex justify-end gap-2">
        {dirty && <button className="btn-ghost" onClick={() => setPicked(new Set(profile.followedSourceIds))}>Undo</button>}
        <button className="btn-primary" onClick={save} disabled={!dirty || saving || picked.size === 0}>
          {saving && <Spinner />} Save sources
        </button>
      </div>
    </section>
  );
}
