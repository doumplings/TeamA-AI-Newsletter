import type { ChannelType } from '../types';

// Client-side checks run before any request is sent (RegisterPage.validateForm).
// The server runs the same checks again; the client copy is only for fast feedback.

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const DISCORD_WEBHOOK_RE = /^https:\/\/(?:ptb\.|canary\.)?(?:discord|discordapp)\.com\/api\/webhooks\/\d+\/[\w-]+$/;

export function validateEmail(email: string): string | null {
  if (!email.trim()) return 'Enter your email address.';
  if (!EMAIL_RE.test(email.trim())) return 'That does not look like an email address.';
  return null;
}

export function validatePassword(password: string): string | null {
  if (password.length < 8) return 'Use at least 8 characters.';
  return null;
}

export function validateContact(type: ChannelType, contact: string): string | null {
  const c = contact.trim();
  if (type === 'email') return validateEmail(c);
  if (type === 'discord') {
    if (!c) return 'Paste your Discord webhook URL.';
    if (!DISCORD_WEBHOOK_RE.test(c)) return 'Should look like https://discord.com/api/webhooks/123.../abc...';
    return null;
  }
  return null;
}

/** Hide most of a contact so the full value is never shown back (ChannelView.maskedContact). */
export function maskContact(type: ChannelType, contact: string): string {
  if (type === 'email') {
    const [name, domain] = contact.split('@');
    return `${name.slice(0, 2)}${'•'.repeat(Math.max(1, name.length - 2))}@${domain}`;
  }
  if (type === 'discord') {
    const id = contact.split('/webhooks/')[1]?.split('/')[0] ?? '';
    return `Webhook •••${id.slice(-4)}`;
  }
  return `Telegram chat •••${contact.slice(-3)}`;
}
