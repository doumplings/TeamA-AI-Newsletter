import { useState, type FormEvent } from 'react';
import { api } from '../api';
import { Alert, Field, PageSpinner, Spinner } from '../components/ui';
import { useToast } from '../context/ToastContext';
import { errorMessage, fieldErrors } from '../lib/errors';
import { timeAgo, useLoad } from '../lib/useLoad';
import type { AdminSourceRequest, AdminSourceView, SourceType } from '../types';

const SOURCE_TYPES: SourceType[] = ['rss', 'html', 'api'];

/** The three standard source-point levels (Table 6-6a). A custom value is added when editing. */
const POINT_CHOICES = [
  { value: 30, label: '30 Official AI company' },
  { value: 20, label: '20 Technology news site' },
  { value: 10, label: '10 Community' },
];

/** The server may name fields in snake_case; the form uses camelCase. */
const FIELD_ALIASES: Record<string, string> = { source_type: 'sourceType', base_weight: 'baseWeight', terms_url: 'termsUrl', is_active: 'isActive' };

/**
 * Manage monitored sources (UC-9, admin only):
 * every source with its health, plus add, edit, on/off and remove.
 */
export default function AdminSourcesPage() {
  const toast = useToast();
  const { data, error, loading, setData } = useLoad(() => api.adminListSources());
  // null = form closed, 'new' = adding, a source = editing that source
  const [editing, setEditing] = useState<AdminSourceView | 'new' | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  if (loading) return <PageSpinner />;
  if (error || !data) return <Alert>{error ?? 'Could not load the sources.'}</Alert>;

  function replace(updated: AdminSourceView) {
    setData((d) => d && d.map((s) => (s.sourceId === updated.sourceId ? updated : s)));
  }

  async function toggleActive(s: AdminSourceView) {
    setBusyId(s.sourceId);
    try {
      replace(await api.adminUpdateSource(s.sourceId, { isActive: !s.isActive }));
      toast(`${s.name} turned ${s.isActive ? 'off' : 'on'}`, 'success');
    } catch (e) {
      toast(errorMessage(e), 'error');
    } finally {
      setBusyId(null);
    }
  }

  async function remove(s: AdminSourceView) {
    if (!window.confirm(`Remove ${s.name}? This cannot be undone.`)) return;
    setBusyId(s.sourceId);
    try {
      await api.adminDeleteSource(s.sourceId);
      setData((d) => d && d.filter((x) => x.sourceId !== s.sourceId));
      toast(`${s.name} removed`);
    } catch (e) {
      toast(errorMessage(e), 'error'); // 409: it has collected news, so the message says to disable it
    } finally {
      setBusyId(null);
    }
  }

  function saved(s: AdminSourceView) {
    setData((d) => {
      if (!d) return d;
      return d.some((x) => x.sourceId === s.sourceId) ? d.map((x) => (x.sourceId === s.sourceId ? s : x)) : [...d, s];
    });
    toast(editing === 'new' ? `${s.name} added` : `${s.name} saved`, 'success');
    setEditing(null);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Sources</h1>
          <p className="text-sm text-slate-600">Websites the collector watches for AI news. {data.filter((s) => s.isActive).length} of {data.length} are on.</p>
        </div>
        {editing === null && <button className="btn-primary" onClick={() => setEditing('new')}>Add source</button>}
      </div>

      {editing !== null && (
        <SourceForm
          // A new key resets the form when switching between sources
          key={editing === 'new' ? 'new' : editing.sourceId}
          source={editing === 'new' ? null : editing}
          onSaved={saved}
          onCancel={() => setEditing(null)}
        />
      )}

      {data.length === 0 ? (
        <div className="card px-6 py-16 text-center">
          <p className="font-semibold">No sources yet</p>
          <p className="mt-1 text-sm text-slate-500">Add a source so the collector has something to read.</p>
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-5 py-3 font-semibold">Source</th>
                <th className="px-3 py-3 font-semibold">Points</th>
                <th className="px-3 py-3 font-semibold">Status</th>
                <th className="px-3 py-3 font-semibold">Last checked</th>
                <th className="px-3 py-3 font-semibold">Problems</th>
                <th className="px-3 py-3 text-right font-semibold">Items</th>
                <th className="px-5 py-3 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((s) => (
                <tr key={s.sourceId} className="hover:bg-slate-50">
                  <td className="max-w-xs px-5 py-3">
                    <p className="font-medium text-slate-900">{s.name} <span className="ml-1 rounded bg-slate-100 px-1.5 py-0.5 text-xs font-semibold uppercase text-slate-600">{s.sourceType}</span></p>
                    <a href={s.url} target="_blank" rel="noreferrer" className="block truncate text-xs text-slate-500 hover:text-indigo-700 hover:underline" title={s.url}>{s.url}</a>
                  </td>
                  <td className="px-3 py-3">{s.baseWeight}</td>
                  <td className="px-3 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${s.isActive ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                      {s.isActive ? 'Active' : 'Off'}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 text-slate-500">{timeAgo(s.lastCheckedAt)}</td>
                  <td className="max-w-xs px-3 py-3">
                    {s.consecutiveFailures > 0 ? (
                      <div>
                        <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-700">
                          {s.consecutiveFailures} failure{s.consecutiveFailures === 1 ? '' : 's'} in a row
                        </span>
                        {s.lastError && <p className="mt-1 truncate text-xs text-rose-600" title={s.lastError}>{s.lastError}</p>}
                      </div>
                    ) : (
                      <span className="text-slate-400">None</span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-right">{s.itemCount}</td>
                  <td className="whitespace-nowrap px-5 py-3 text-right">
                    <div className="inline-flex items-center gap-1">
                      {busyId === s.sourceId && <Spinner className="h-4 w-4 text-slate-400" />}
                      <button className="btn-ghost px-2.5 py-1.5" onClick={() => toggleActive(s)} disabled={busyId === s.sourceId}>{s.isActive ? 'Turn off' : 'Turn on'}</button>
                      <button className="btn-ghost px-2.5 py-1.5" onClick={() => setEditing(s)} disabled={busyId === s.sourceId}>Edit</button>
                      <button className="btn-danger px-2.5 py-1.5" onClick={() => remove(s)} disabled={busyId === s.sourceId}>Remove</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** Add or edit one source. Edit sends only what changed; add sends everything. */
function SourceForm({ source, onSaved, onCancel }: { source: AdminSourceView | null; onSaved: (s: AdminSourceView) => void; onCancel: () => void }) {
  const [name, setName] = useState(source?.name ?? '');
  const [sourceType, setSourceType] = useState<SourceType>(source?.sourceType ?? 'rss');
  const [url, setUrl] = useState(source?.url ?? '');
  const [baseWeight, setBaseWeight] = useState(source?.baseWeight ?? 20);
  const [termsUrl, setTermsUrl] = useState(source?.termsUrl ?? '');
  const [isActive, setIsActive] = useState(source?.isActive ?? true);
  const [configText, setConfigText] = useState(source && Object.keys(source.config).length > 0 ? JSON.stringify(source.config, null, 2) : '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // When editing a source with a non-standard value, show that value as a fourth choice.
  const choices = POINT_CHOICES.some((c) => c.value === baseWeight) ? POINT_CHOICES : [...POINT_CHOICES, { value: baseWeight, label: `${baseWeight} Custom` }];

  async function submit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);

    const found: Record<string, string> = {};
    if (!name.trim()) found.name = 'Enter a name.';
    if (!url.trim()) found.url = 'Enter the address of the feed or page.';
    if (!termsUrl.trim()) found.termsUrl = 'The terms-of-use page is required.';

    let config: Record<string, unknown> = {};
    if (configText.trim()) {
      try {
        const parsed: unknown = JSON.parse(configText);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) throw new Error();
        config = parsed as Record<string, unknown>;
      } catch {
        found.config = 'Must be valid JSON describing an object, like {"item_selector": "article"}.';
      }
    }
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const body: AdminSourceRequest = { name: name.trim(), sourceType, url: url.trim(), baseWeight, isActive, termsUrl: termsUrl.trim(), config };
    setSaving(true);
    try {
      onSaved(source ? await api.adminUpdateSource(source.sourceId, body) : await api.adminAddSource(body));
    } catch (err) {
      const raw = fieldErrors(err);
      const mapped: Record<string, string> = {};
      for (const [k, v] of Object.entries(raw)) mapped[FIELD_ALIASES[k] ?? k] = v;
      setErrors(mapped);
      setFormError(errorMessage(err));
      setSaving(false);
    }
  }

  const cls = (field: string) => `input ${errors[field] ? 'input-error' : ''}`;

  return (
    <form onSubmit={submit} noValidate className="card space-y-4 p-5">
      <h2 className="font-semibold">{source ? `Edit ${source.name}` : 'Add a source'}</h2>
      {formError && <Alert>{formError}</Alert>}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" htmlFor="src-name" error={errors.name}>
          <input id="src-name" className={cls('name')} value={name} onChange={(e) => setName(e.target.value)} placeholder="Example AI Blog" />
        </Field>
        <Field label="Type" htmlFor="src-type" error={errors.sourceType}>
          <select id="src-type" className={cls('sourceType')} value={sourceType} onChange={(e) => setSourceType(e.target.value as SourceType)}>
            {SOURCE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </Field>
      </div>

      <Field label="URL" htmlFor="src-url" error={errors.url}>
        <input id="src-url" className={cls('url')} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/feed.xml" inputMode="url" />
      </Field>

      <div>
        <span className="label" id="src-points-label">Source points</span>
        <div role="radiogroup" aria-labelledby="src-points-label" className="inline-flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1">
          {choices.map((c) => (
            <button
              key={c.value}
              type="button"
              role="radio"
              aria-checked={baseWeight === c.value}
              onClick={() => setBaseWeight(c.value)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                baseWeight === c.value ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        {errors.baseWeight && <p className="mt-1.5 text-sm text-rose-600">{errors.baseWeight}</p>}
      </div>

      <Field label="Terms-of-use URL" htmlFor="src-terms" error={errors.termsUrl} hint="The collector only fetches sources whose terms you have reviewed.">
        <input id="src-terms" className={cls('termsUrl')} value={termsUrl} onChange={(e) => setTermsUrl(e.target.value)} placeholder="https://example.com/terms" inputMode="url" />
      </Field>

      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <input type="checkbox" className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
        Active (the collector checks this source)
      </label>

      <Field
        label="Advanced settings (JSON, optional)"
        htmlFor="src-config"
        error={errors.config}
        hint="HTML sources need item_selector, title_selector and link_selector so the collector knows where the stories are."
      >
        <textarea id="src-config" rows={4} className={`${cls('config')} font-mono`} value={configText} onChange={(e) => setConfigText(e.target.value)} placeholder='{"item_selector": "article", "title_selector": "h2", "link_selector": "a"}' />
      </Field>

      <div className="flex justify-end gap-2">
        <button type="button" className="btn-ghost" onClick={onCancel} disabled={saving}>Cancel</button>
        <button type="submit" className="btn-primary" disabled={saving}>{saving && <Spinner />} {source ? 'Save changes' : 'Add source'}</button>
      </div>
    </form>
  );
}
