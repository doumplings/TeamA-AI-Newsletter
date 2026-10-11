import axios, { AxiosError, type AxiosInstance } from 'axios';
import type { ApiClient } from './ApiClient';
import { ApiError } from './ApiClient';
import type {
  AccountView,
  ChannelChanges,
  ChannelType,
  ChannelView,
  HistoryPageView,
  ImportanceLevel,
  ProfileView,
  SendTestResult,
  SourceView,
  TelegramLinkView,
  VerifyResult,
} from '../types';

/**
 * Live client: real HTTP calls to the FastAPI Web API.
 * The endpoints are the ones listed for ApiClient in Section 8.2.
 */
export class HttpApiClient implements ApiClient {
  readonly mode = 'live' as const;
  private http: AxiosInstance;

  constructor(baseUrl = '/api') {
    this.http = axios.create({
      baseURL: baseUrl,
      withCredentials: true, // send the HTTP-only session cookie
      timeout: 20000,
    });

    // Turn every server error into one ApiError shape for the pages.
    this.http.interceptors.response.use(
      (res) => res,
      (err: AxiosError<{ detail?: unknown }>) => {
        throw toApiError(err);
      },
    );
  }

  // ---- Auth ----
  async register(email: string, password: string) {
    return (await this.http.post<AccountView>('/auth/register', { email, password })).data;
  }
  async login(email: string, password: string) {
    return (await this.http.post<AccountView>('/auth/login', { email, password })).data;
  }
  async logout() {
    await this.http.post('/auth/logout');
  }
  async me() {
    try {
      return (await this.http.get<AccountView>('/auth/me')).data;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return null;
      throw e;
    }
  }

  // ---- Channels ----
  async getChannels() {
    return (await this.http.get<ChannelView[]>('/channels')).data;
  }
  async addChannel(channelType: ChannelType, contact: string) {
    return (await this.http.post<ChannelView>('/channels', { channelType, contact })).data;
  }
  async sendTestCode(channelId: number) {
    return (await this.http.post<SendTestResult>(`/channels/${channelId}/test`)).data;
  }
  async confirmCode(channelId: number, code: string) {
    return (await this.http.post<VerifyResult>(`/channels/${channelId}/verify`, { code })).data;
  }
  async updateChannel(channelId: number, changes: ChannelChanges) {
    return (await this.http.patch<ChannelView>(`/channels/${channelId}`, changes)).data;
  }
  async deleteChannel(channelId: number) {
    await this.http.delete(`/channels/${channelId}`);
  }
  async startTelegramLink() {
    return (await this.http.post<TelegramLinkView>('/channels/telegram/link')).data;
  }

  // ---- Profile and sources ----
  async getProfile() {
    return (await this.http.get<ProfileView>('/profile')).data;
  }
  async setThreshold(level: ImportanceLevel) {
    return (await this.http.put<ProfileView>('/profile/threshold', { level })).data;
  }
  async setFollowedSources(sourceIds: number[]) {
    return (await this.http.put<ProfileView>('/profile/sources', { sourceIds })).data;
  }
  async getSources() {
    return (await this.http.get<SourceView[]>('/sources')).data;
  }

  // ---- History ----
  async getHistory(page: number) {
    return (await this.http.get<HistoryPageView>('/history', { params: { page } })).data;
  }
  async sendSampleNews() {
    return (await this.http.post<{ delivered: number; failed: number }>('/deliveries/sample')).data;
  }
}

/**
 * FastAPI errors come back as {"detail": "..."} for our own errors, or
 * {"detail": [{loc, msg}, ...]} for request validation errors.
 */
function toApiError(err: AxiosError<{ detail?: unknown }>): ApiError {
  if (!err.response) {
    return new ApiError('Cannot reach the server. Is the API running?', 0);
  }
  const { status, data } = err.response;
  const detail = data?.detail;

  if (typeof detail === 'string') return new ApiError(detail, status);

  if (Array.isArray(detail)) {
    const fields: Record<string, string> = {};
    for (const d of detail as { loc?: unknown[]; msg?: string }[]) {
      const field = String(d.loc?.[d.loc.length - 1] ?? 'form');
      fields[field] = d.msg ?? 'Invalid value';
    }
    return new ApiError('Please check the highlighted fields.', status, fields);
  }

  if (detail && typeof detail === 'object') {
    const d = detail as { message?: string; fields?: Record<string, string> };
    return new ApiError(d.message ?? 'Request failed', status, d.fields ?? {});
  }

  return new ApiError(`Request failed (${status})`, status);
}
