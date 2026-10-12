import { useState } from 'react';
import { api } from '../api';
import { ChannelConnector } from '../components/ChannelConnector';
import { LevelPicker } from '../components/LevelPicker';
import { Alert, ChannelIcon, PageSpinner, Spinner } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { errorMessage } from '../lib/errors';
import { useLoad } from '../lib/useLoad';
import type { ChannelChanges, ChannelType, ChannelView, ImportanceLevel } from '../types';
import { CHANNEL_LABEL } from '../types';

const TYPES: ChannelType[] = ['telegram', 'discord', 'email'];

/**
 * Notifications section of the dashboard (Figure 39, UC-4, UC-5, UC-6).
 *  - one row per channel type with its status, its own level, and on/off
 *  - a channel that is not connected shows its contact field right in the row (Change 5)
 *  - a new channel is saved as soon as it is verified (Change 8)
 *  - level and on/off edits are saved together with one "Save changes" button
 */
export default function NotificationsPage() {
  const { account } = useAuth();
  const toast = useToast();

  const { data, error, loading, setData } = useLoad(async () => {
    const [channels, profile] = await Promise.all([api.getChannels(), api.getProfile()]);
    return { channels, profile };
  });

  const [pending, setPending] = useState<Record<number, ChannelChanges>>({});
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [removing, setRemoving] = useState<number | null>(null);

  if (loading) return <PageSpinner />;
  if (error || !data) return <Alert>{error ?? 'Could not load your channels.'}</Alert>;

  const dirtyCount = Object.keys(pending).length;

  /** Current value for a channel: unsaved edit if there is one, else what the server has. */
  function current(ch: ChannelView): ChannelChanges {
    return pending[ch.channelId] ?? { isEnabled: ch.isEnabled, minImportance: ch.minImportance };
  }

  function edit(ch: ChannelView, patch: Partial<ChannelChanges>) {
    setSavedAt(null);
    const next = { ...current(ch), ...patch };
    setPending((p) => {
      const copy = { ...p };
      // If the edit puts things back the way they were, it is no longer pending.
      if (next.isEnabled === ch.isEnabled && next.minImportance === ch.minImportance) delete copy[ch.channelId];
      else copy[ch.channelId] = next;
      return copy;
    });
  }

  async function saveChanges() {
    setSaving(true);
    try {
      const updated = await Promise.all(Object.entries(pending).map(([id, ch]) => api.updateChannel(Number(id), ch)));
      setData((d) => d && { ...d, channels: d.channels.map((c) => updated.find((u) => u.channelId === c.channelId) ?? c) });
      setPending({});
      setSavedAt(Date.now());
    } catch (e) {
      toast(errorMessage(e), 'error');
    } finally {
      setSaving(false);
    }
  }

  function onConnected(ch: ChannelView) {
    toast(`${CHANNEL_LABEL[ch.channelType]} connected`, 'success');
    setData((d) => d && { ...d, channels: [...d.channels.filter((c) => c.channelType !== ch.channelType), ch] });
  }

  async function remove(ch: ChannelView) {
    if (!window.confirm(`Disconnect ${CHANNEL_LABEL[ch.channelType]}? You will stop getting news there.`)) return;
    setRemoving(ch.channelId);
    try {
      await api.deleteChannel(ch.channelId);
      setData((d) => d && { ...d, channels: d.channels.filter((c) => c.channelId !== ch.channelId) });
      setPending((p) => {
        const copy = { ...p };
        delete copy[ch.channelId];
        return copy;
      });
      toast(`${CHANNEL_LABEL[ch.channelType]} disconnected`);
    } catch (e) {
      toast(errorMessage(e), 'error');
    } finally {
      setRemoving(null);
    }
  }

  const defaultLevel: ImportanceLevel = data.profile.defaultThreshold;

  return (
    <div className="space-y-6 pb-20">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Notifications</h1>
        <p className="text-sm text-slate-600">Choose where news goes and how important it must be for each channel.</p>
      </div>

      <ul className="space-y-4">
        {TYPES.map((type) => {
          const ch = data.channels.find((c) => c.channelType === type && c.isVerified);
          const values = ch ? current(ch) : null;
          const isDirty = ch ? pending[ch.channelId] !== undefined : false;
          return (
            <li key={type} className={`card p-5 ${isDirty ? 'ring-2 ring-amber-300' : ''}`}>
              <div className="flex flex-wrap items-center gap-3">
                <ChannelIcon type={type} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h2 className="font-semibold">{CHANNEL_LABEL[type]}</h2>
                    <StatusPill channel={ch} enabled={values?.isEnabled} />
                  </div>
                  <p className="truncate text-sm text-slate-500">{ch ? ch.maskedContact : 'Not connected yet'}</p>
                </div>
                {ch && values && (
                  <div className="flex w-full items-center justify-end gap-3 sm:w-auto">
                    <Toggle label={`${CHANNEL_LABEL[type]} on or off`} checked={values.isEnabled} onChange={(v) => edit(ch, { isEnabled: v })} />
                    <button className="btn-danger px-2 py-1.5 text-xs" onClick={() => remove(ch)} disabled={removing === ch.channelId}>
                      {removing === ch.channelId ? <Spinner /> : 'Remove'}
                    </button>
                  </div>
                )}
              </div>

              <div className="mt-4 border-t border-slate-100 pt-4">
                {ch && values ? (
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="text-sm font-medium text-slate-700">Send me:</span>
                    <LevelPicker
                      name={`${CHANNEL_LABEL[type]} importance level`}
                      value={values.minImportance}
                      onChange={(lvl) => edit(ch, { minImportance: lvl })}
                      allowDefault
                      defaultLevel={defaultLevel}
                      disabled={!values.isEnabled}
                    />
                  </div>
                ) : (
                  <ChannelConnector
                    type={type}
                    defaultContact={type === 'email' ? account?.email ?? '' : ''}
                    onConnected={onConnected}
                  />
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {/* Save bar: only level and on/off changes need saving (Change 8) */}
      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-end gap-3 px-4 py-3 sm:px-6" aria-live="polite">
          {savedAt && dirtyCount === 0 && <span className="text-sm font-medium text-emerald-600">✓ Changes saved</span>}
          {dirtyCount > 0 && (
            <>
              <span className="text-sm text-slate-600">{dirtyCount} unsaved {dirtyCount === 1 ? 'change' : 'changes'}</span>
              <button className="btn-ghost" onClick={() => setPending({})} disabled={saving}>Discard</button>
            </>
          )}
          <button className="btn-primary" onClick={saveChanges} disabled={dirtyCount === 0 || saving}>
            {saving && <Spinner />} Save changes
          </button>
        </div>
      </div>
    </div>
  );
}

function StatusPill({ channel, enabled }: { channel?: ChannelView; enabled?: boolean }) {
  if (!channel) return <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">Not connected</span>;
  if (!enabled) return <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">Paused</span>;
  return <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">Connected</span>;
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 rounded-full transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 ${checked ? 'bg-indigo-600' : 'bg-slate-300'}`}
    >
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${checked ? 'left-[22px]' : 'left-0.5'}`} />
    </button>
  );
}
