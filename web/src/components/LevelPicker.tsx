import type { ImportanceLevel } from '../types';
import { LEVEL_LABEL } from '../types';

const ORDER: ImportanceLevel[] = ['high', 'medium', 'low'];

/**
 * Three labelled buttons instead of a slider (Section 10.2, Change 6):
 * one click, works well on phones and with a keyboard.
 * Pass allowDefault to add a "Use default" option for per-channel levels.
 */
export function LevelPicker({
  value,
  onChange,
  allowDefault = false,
  defaultLevel,
  disabled = false,
  name,
}: {
  value: ImportanceLevel | null;
  onChange: (level: ImportanceLevel | null) => void;
  allowDefault?: boolean;
  defaultLevel?: ImportanceLevel;
  disabled?: boolean;
  name: string;
}) {
  const options: (ImportanceLevel | null)[] = allowDefault ? [null, ...ORDER] : ORDER;
  return (
    <div role="radiogroup" aria-label={name} className="inline-flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1">
      {options.map((opt) => {
        const selected = value === opt;
        const label = opt === null ? `Default${defaultLevel ? ` (${LEVEL_LABEL[defaultLevel]})` : ''}` : LEVEL_LABEL[opt];
        return (
          <button
            key={opt ?? 'default'}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(opt)}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:opacity-50 ${
              selected ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
