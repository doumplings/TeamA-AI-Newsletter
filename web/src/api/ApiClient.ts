import type {
  AccountView,
  AdminSourceRequest,
  AdminSourceView,
  ChannelChanges,
  ChannelType,
  ChannelView,
  HistoryPageView,
  ImportanceLevel,
  NewsView,
  PipelineStatusView,
  ProfileView,
  SendTestResult,
  SourceView,
  TelegramLinkView,
  VerifyResult,
} from '../types';

/**
 * Every page talks to the server only through this interface (Section 8, ApiClient).
 *
 * There are two implementations with the same methods:
 *   - HttpApiClient: real calls with Axios to the FastAPI Web API
 *   - MockApiClient: fake data kept in localStorage, no server needed
 *
 * Because the pages only know this interface, switching from fake data to the
 * live server is one line in .env (VITE_API_MODE) and no page code changes.
 */
export interface ApiClient {
  readonly mode: 'mock' | 'live';

  // Auth (UC-2, UC-3)
  register(email: string, password: string): Promise<AccountView>;
  login(email: string, password: string): Promise<AccountView>;
  logout(): Promise<void>;
  me(): Promise<AccountView | null>;

  // Channels (UC-4, UC-5)
  getChannels(): Promise<ChannelView[]>;
  addChannel(type: ChannelType, contact: string): Promise<ChannelView>;
  sendTestCode(channelId: number): Promise<SendTestResult>;
  confirmCode(channelId: number, code: string): Promise<VerifyResult>;
  updateChannel(channelId: number, changes: ChannelChanges): Promise<ChannelView>;
  deleteChannel(channelId: number): Promise<void>;
  startTelegramLink(): Promise<TelegramLinkView>;

  // Profile and sources (UC-6, UC-7)
  getProfile(): Promise<ProfileView>;
  setThreshold(level: ImportanceLevel): Promise<ProfileView>;
  setFollowedSources(sourceIds: number[]): Promise<ProfileView>;
  getSources(): Promise<SourceView[]>;

  /** Newest collected news from the sources the subscriber follows. */
  getNews(limit?: number): Promise<NewsView[]>;

  // History (UC-8)
  getHistory(page: number): Promise<HistoryPageView>;

  /** Sends one sample news item to every verified channel, so you can see delivery work. */
  sendSampleNews(): Promise<{ delivered: number; failed: number }>;

  // Source administration (UC-9) and pipeline status; admin accounts only (server answers 403 otherwise)
  adminListSources(): Promise<AdminSourceView[]>;
  /** 409 = URL already registered; 422 carries field errors. */
  adminAddSource(req: AdminSourceRequest): Promise<AdminSourceView>;
  adminUpdateSource(sourceId: number, changes: Partial<AdminSourceRequest>): Promise<AdminSourceView>;
  /** 409 = the source has collected news, disable it instead. */
  adminDeleteSource(sourceId: number): Promise<void>;
  adminPipelineStatus(): Promise<PipelineStatusView>;
}

/** Error thrown by both clients, so pages can show it the same way. */
export class ApiError extends Error {
  status: number;
  fieldErrors: Record<string, string>;

  constructor(message: string, status = 400, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}
