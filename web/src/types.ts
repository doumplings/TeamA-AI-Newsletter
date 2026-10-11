// Data shapes shared with the Web API.
// These mirror Table 8-3 (enumerations) and Table 8-4 (request and view types)
// in Report 2 Part 2, so the client and the FastAPI server speak the same JSON.

export type Role = 'subscriber' | 'admin';
export type ImportanceLevel = 'low' | 'medium' | 'high';
export type ChannelType = 'telegram' | 'email' | 'discord';
export type DeliveryStatus = 'queued' | 'sent' | 'failed' | 'permanent_failure';
export type SourceType = 'rss' | 'html' | 'api';

export interface AccountView {
  userId: number;
  email: string;
  role: Role;
}

export interface ChannelView {
  channelId: number;
  channelType: ChannelType;
  maskedContact: string;
  isEnabled: boolean;
  isVerified: boolean;
  /** null means "use the default threshold from the profile". */
  minImportance: ImportanceLevel | null;
}

export interface ChannelChanges {
  isEnabled: boolean;
  minImportance: ImportanceLevel | null;
}

export interface ProfileView {
  defaultThreshold: ImportanceLevel;
  followedSourceIds: number[];
}

export interface SourceView {
  sourceId: number;
  name: string;
  sourceType: SourceType;
  url: string;
  baseWeight: number;
  isActive: boolean;
}

export interface DeliveryView {
  deliveryId: number;
  title: string;
  link: string;
  sourceName: string;
  importanceLevel: ImportanceLevel;
  channelType: ChannelType;
  status: DeliveryStatus;
  sentAt: string | null;
}

export interface HistoryPageView {
  items: DeliveryView[];
  page: number;
  totalPages: number;
}

/** Result of POST /channels/{id}/verify. */
export interface VerifyResult {
  ok: boolean;
  attemptsLeft: number;
  channel?: ChannelView;
}

/** Result of POST /channels/telegram/link (Section 10.2, Change 1). */
export interface TelegramLinkView {
  url: string;
  expiresInSeconds: number;
}

/** Result of POST /channels/{id}/test. In mock mode the code is returned so you can demo it. */
export interface SendTestResult {
  sent: boolean;
  demoCode?: string;
}

export const LEVEL_LABEL: Record<ImportanceLevel, string> = {
  high: 'High only',
  medium: 'Medium and up',
  low: 'Everything',
};

export const CHANNEL_LABEL: Record<ChannelType, string> = {
  telegram: 'Telegram',
  email: 'Email',
  discord: 'Discord',
};
