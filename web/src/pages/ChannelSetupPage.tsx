import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AuthLayout } from '../components/AuthLayout';
import { ChannelConnector } from '../components/ChannelConnector';
import { ChannelIcon } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import type { ChannelType, ChannelView } from '../types';
import { CHANNEL_LABEL } from '../types';

const OPTIONS: { type: ChannelType; blurb: string }[] = [
  { type: 'telegram', blurb: 'Fastest. One tap, no code.' },
  { type: 'discord', blurb: 'Post into a server channel.' },
  { type: 'email', blurb: 'Sent to your inbox.' },
];

/**
 * Step 2 of sign-up: pick and connect the first channel (Figure 38).
 * There is no "Finish setup" button: the dashboard opens by itself as soon as
 * the first channel is verified (Section 10.2, Change 4).
 */
export default function ChannelSetupPage() {
  const { account } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [selected, setSelected] = useState<ChannelType | null>(null);

  function onConnected(ch: ChannelView) {
    toast(`${CHANNEL_LABEL[ch.channelType]} connected`, 'success');
    navigate('/dashboard', { replace: true, state: { justConnected: ch.channelType } });
  }

  return (
    <AuthLayout
      step="Step 2 of 2"
      title="Where should we send your news?"
      subtitle="Pick one to start. You can add the others later from your dashboard."
      footer={<Link to="/dashboard" className="text-slate-500 hover:text-slate-700 hover:underline">Skip for now</Link>}
    >
      <div className="space-y-3" role="radiogroup" aria-label="Notification channel">
        {OPTIONS.map(({ type, blurb }) => {
          const isOpen = selected === type;
          return (
            <div key={type} className={`rounded-xl border transition ${isOpen ? 'border-indigo-500 ring-2 ring-indigo-500/15' : 'border-slate-200 hover:border-slate-300'}`}>
              <button
                type="button"
                role="radio"
                aria-checked={isOpen}
                onClick={() => setSelected(type)}
                className="flex w-full items-center gap-3 rounded-xl p-4 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
              >
                <ChannelIcon type={type} />
                <span className="flex-1">
                  <span className="block font-semibold">{CHANNEL_LABEL[type]}</span>
                  <span className="block text-sm text-slate-500">{blurb}</span>
                </span>
                <span className={`h-4 w-4 rounded-full border-2 ${isOpen ? 'border-indigo-600 bg-indigo-600 shadow-[inset_0_0_0_3px_white]' : 'border-slate-300'}`} />
              </button>
              {isOpen && (
                <div className="border-t border-slate-100 p-4">
                  <ChannelConnector
                    type={type}
                    // Change 2: email is pre-filled with the sign-up address
                    defaultContact={type === 'email' ? account?.email ?? '' : ''}
                    onConnected={onConnected}
                    autoFocus={type === 'discord'}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </AuthLayout>
  );
}
