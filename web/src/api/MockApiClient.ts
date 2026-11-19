import type { ApiClient } from './ApiClient';
import { ApiError } from './ApiClient';
import { FAKE_NEWS, FAKE_SOURCES, slugLink } from './fakeData';
import type {
  AccountView,
  AdminSourceRequest,
  AdminSourceView,
  CycleRunView,
  ChannelChanges,
  ChannelType,
  ChannelView,
  DeliveryView,
  ImportanceLevel,
  NewsView,
  PipelineStatusView,
  ProfileView,
  SourceView,
} from '../types';
import { maskContact, validateContact, validateEmail } from '../lib/validation';

/**
 * Fake-data client. It follows the same rules the real server will
 * (Section 8, ChannelVerifier: 6-digit code, 10-minute lifetime, 3 wrong tries),
 * so the screens behave the same in both modes. Data lives in localStorage so a
 * page refresh does not lose it.
 */

const DB_KEY = 'ainews-mock-db-v1';
const PAGE_SIZE = 10;
const CODE_LIFETIME_MS = 10 * 60 * 1000;
const MAX_ATTEMPTS = 3;

interface MockChannel extends ChannelView {
  userId: number;
  contact: string;
  code: string | null;
  codeExpiresAt: number | null;
  attemptsLeft: number;
}

interface MockDb {
  nextId: number;
  users: { userId: number; email: string; password: string }[];
  sessionUserId: number | null;
  channels: MockChannel[];
  profiles: Record<number, ProfileView>;
  deliveries: (DeliveryView & { userId: number })[];
  /** Source list the admin screens edit. Missing in databases saved before UC-9, so it is filled on first use. */
  adminSources?: AdminSourceView[];
}

const emptyDb = (): MockDb => ({
  nextId: 1,
  users: [],
  sessionUserId: null,
  channels: [],
  profiles: {},
  deliveries: [],
});

function loadDb(): MockDb {
  try {
    const raw = localStorage.getItem(DB_KEY);
    return raw ? (JSON.parse(raw) as MockDb) : emptyDb();
  } catch {
    return emptyDb();
  }
}

/** Starting list for the admin screens: the fake sources plus believable collector state. */
function seedAdminSources(): AdminSourceView[] {
  const now = Date.now();
  return FAKE_SOURCES.map((s, i) => {
    const failing = s.sourceId === 4; // one source that is having trouble, so the error column has something to show
    return {
      ...s,
      termsUrl: `${new URL(s.url).origin}/terms`,
      config: s.sourceType === 'html' ? { item_selector: 'article', title_selector: 'h2', link_selector: 'a' } : {},
      lastCheckedAt: new Date(now - (i + 1) * 4 * 60 * 1000).toISOString(),
      lastSuccessAt: new Date(now - (failing ? 3 * 3600 * 1000 : (i + 1) * 4 * 60 * 1000)).toISOString(),
      consecutiveFailures: failing ? 3 : 0,
      lastError: failing ? 'HTTP 503 from the source' : null,
      itemCount: FAKE_NEWS.filter((n) => n.sourceId === s.sourceId).length,
    };
  });
}

const wait = (ms = 350) => new Promise((r) => setTimeout(r, ms));

export class MockApiClient implements ApiClient {
  readonly mode = 'mock' as const;
  private db: MockDb = loadDb();

  private save() {
    try {
      localStorage.setItem(DB_KEY, JSON.stringify(this.db));
    } catch {
      /* private window: keep data in memory only */
    }
  }

  private id() {
    return this.db.nextId++;
  }

  private requireUser(): number {
    if (this.db.sessionUserId == null) throw new ApiError('Please log in again.', 401);
    return this.db.sessionUserId;
  }

  private myChannel(channelId: number): MockChannel {
    const userId = this.requireUser();
    const ch = this.db.channels.find((c) => c.channelId === channelId && c.userId === userId);
    if (!ch) throw new ApiError('Channel not found.', 404);
    return ch;
  }

  /** The admin source list, created from the fake sources the first time it is needed. */
  private sources(): AdminSourceView[] {
    if (!this.db.adminSources) this.db.adminSources = seedAdminSources();
    return this.db.adminSources;
  }

  private findSource(sourceId: number): AdminSourceView {
    const src = this.sources().find((x) => x.sourceId === sourceId);
    if (!src) throw new ApiError('Source not found.', 404);
    return src;
  }

  /** Same checks the server makes on a source; returns field errors, empty when fine. */
  private checkSource(req: Partial<AdminSourceRequest>): Record<string, string> {
    const errs: Record<string, string> = {};
    if (req.name !== undefined && !req.name.trim()) errs.name = 'Name is required.';
    for (const key of ['url', 'termsUrl'] as const) {
      const value = req[key];
      if (value === undefined) continue;
      try {
        if (!/^https?:$/.test(new URL(value).protocol)) throw new Error();
      } catch {
        errs[key] = 'Enter a full web address starting with http:// or https://';
      }
    }
    if (req.baseWeight !== undefined && !(req.baseWeight >= 0 && req.baseWeight <= 30)) errs.baseWeight = 'Must be between 0 and 30.';
    return errs;
  }

  private view(ch: MockChannel): ChannelView {
    const { channelId, channelType, maskedContact, isEnabled, isVerified, minImportance } = ch;
    return { channelId, channelType, maskedContact, isEnabled, isVerified, minImportance };
  }

  // ---------------- Auth ----------------
  async register(email: string, password: string): Promise<AccountView> {
    await wait();
    const emailErr = validateEmail(email);
    if (emailErr) throw new ApiError(emailErr, 422, { email: emailErr });
    if (password.length < 8) throw new ApiError('Password too short.', 422, { password: 'At least 8 characters.' });
    if (this.db.users.some((u) => u.email.toLowerCase() === email.toLowerCase())) {
      throw new ApiError('An account with this email already exists.', 409, { email: 'Already registered. Try logging in.' });
    }
    const userId = this.id();
    this.db.users.push({ userId, email, password });
    this.db.profiles[userId] = { defaultThreshold: 'high', followedSourceIds: FAKE_SOURCES.map((s) => s.sourceId) };
    this.db.sessionUserId = userId;
    this.save();
    return { userId, email, role: 'admin' };
  }

  async login(email: string, password: string): Promise<AccountView> {
    await wait();
    const u = this.db.users.find((x) => x.email.toLowerCase() === email.toLowerCase() && x.password === password);
    if (!u) throw new ApiError('Email or password is incorrect.', 401);
    this.db.sessionUserId = u.userId;
    this.save();
    return { userId: u.userId, email: u.email, role: 'admin' };
  }

  async logout() {
    await wait(150);
    this.db.sessionUserId = null;
    this.save();
  }

  async me(): Promise<AccountView | null> {
    await wait(100);
    const u = this.db.users.find((x) => x.userId === this.db.sessionUserId);
    return u ? { userId: u.userId, email: u.email, role: 'admin' } : null;
  }

  // ---------------- Channels ----------------
  async getChannels() {
    await wait(150);
    const userId = this.requireUser();
    return this.db.channels.filter((c) => c.userId === userId).map((c) => this.view(c));
  }

  async addChannel(type: ChannelType, contact: string) {
    await wait();
    const userId = this.requireUser();
    if (type === 'telegram') throw new ApiError('Telegram is connected with the "Open Telegram" button.', 400);
    const err = validateContact(type, contact);
    if (err) throw new ApiError(err, 422, { contact: err });

    // Re-adding the same type replaces an unverified one instead of making duplicates.
    this.db.channels = this.db.channels.filter((c) => !(c.userId === userId && c.channelType === type && !c.isVerified));

    const ch: MockChannel = {
      channelId: this.id(),
      userId,
      channelType: type,
      contact: contact.trim(),
      maskedContact: maskContact(type, contact.trim()),
      isEnabled: true,
      isVerified: false,
      minImportance: null,
      code: null,
      codeExpiresAt: null,
      attemptsLeft: MAX_ATTEMPTS,
    };
    this.db.channels.push(ch);
    this.save();
    return this.view(ch);
  }

  async sendTestCode(channelId: number) {
    await wait(600);
    const ch = this.myChannel(channelId);
    const code = String(Math.floor(100000 + Math.random() * 900000));
    ch.code = code;
    ch.codeExpiresAt = Date.now() + CODE_LIFETIME_MS;
    ch.attemptsLeft = MAX_ATTEMPTS;
    this.save();
    // Nothing is really sent in mock mode, so the code comes back for the demo.
    return { sent: true, demoCode: code };
  }

  async confirmCode(channelId: number, code: string) {
    await wait(400);
    const ch = this.myChannel(channelId);
    if (!ch.code || !ch.codeExpiresAt || Date.now() > ch.codeExpiresAt || ch.attemptsLeft <= 0) {
      throw new ApiError('This code has expired. Send a new one.', 410);
    }
    if (code !== ch.code) {
      ch.attemptsLeft -= 1;
      if (ch.attemptsLeft <= 0) ch.code = null;
      this.save();
      return { ok: false, attemptsLeft: ch.attemptsLeft };
    }
    ch.isVerified = true;
    ch.code = null;
    this.seedHistoryIfEmpty(ch.userId, ch.channelType);
    this.save();
    return { ok: true, attemptsLeft: ch.attemptsLeft, channel: this.view(ch) };
  }

  async updateChannel(channelId: number, changes: ChannelChanges) {
    await wait();
    const ch = this.myChannel(channelId);
    ch.isEnabled = changes.isEnabled;
    ch.minImportance = changes.minImportance;
    this.save();
    return this.view(ch);
  }

  async deleteChannel(channelId: number) {
    await wait();
    const ch = this.myChannel(channelId);
    this.db.channels = this.db.channels.filter((c) => c !== ch);
    this.save();
  }

  /**
   * Real flow: the user presses Start in Telegram and the bot links the chat.
   * Mock flow: we pretend they pressed Start 3 seconds later.
   */
  async startTelegramLink() {
    await wait();
    const userId = this.requireUser();
    setTimeout(() => {
      this.db = loadDb();
      this.db.channels = this.db.channels.filter((c) => !(c.userId === userId && c.channelType === 'telegram'));
      this.db.channels.push({
        channelId: this.id(),
        userId,
        channelType: 'telegram',
        contact: '123456789',
        maskedContact: 'Telegram chat •••789',
        isEnabled: true,
        isVerified: true,
        minImportance: null,
        code: null,
        codeExpiresAt: null,
        attemptsLeft: MAX_ATTEMPTS,
      });
      this.seedHistoryIfEmpty(userId, 'telegram');
      this.save();
    }, 3000);
    return { url: 'https://t.me/AINewsletterDemoBot?start=mock-token', expiresInSeconds: 600 };
  }

  // ---------------- Profile ----------------
  async getProfile() {
    await wait(150);
    return { ...this.db.profiles[this.requireUser()] };
  }

  async setThreshold(level: ImportanceLevel) {
    await wait();
    const p = this.db.profiles[this.requireUser()];
    p.defaultThreshold = level;
    this.save();
    return { ...p };
  }

  async setFollowedSources(sourceIds: number[]) {
    await wait();
    const p = this.db.profiles[this.requireUser()];
    p.followedSourceIds = [...sourceIds];
    this.save();
    return { ...p };
  }

  async getSources() {
    await wait(150);
    return this.sources()
      .filter((x) => x.isActive)
      .map((x): SourceView => ({ sourceId: x.sourceId, name: x.name, sourceType: x.sourceType, url: x.url, baseWeight: x.baseWeight, isActive: x.isActive }));
  }

  async getNews(limit = 10): Promise<NewsView[]> {
    await wait(200);
    const followed = new Set(this.db.profiles[this.requireUser()].followedSourceIds);
    const now = Date.now();
    return FAKE_NEWS.map((news, i) => ({ news, i }))
      .filter(({ news }) => followed.has(news.sourceId))
      .slice(0, limit)
      .map(({ news, i }) => ({
        itemId: i + 1,
        title: news.title,
        link: slugLink(news.title, news.sourceId),
        sourceName: FAKE_SOURCES.find((s) => s.sourceId === news.sourceId)!.name,
        summary: null,
        importanceLevel: null, // not scored until the classifier is merged
        publishedAt: new Date(now - (i + 1) * 2.5 * 3600 * 1000).toISOString(),
      }));
  }

  // ---------------- History ----------------
  async getHistory(page: number) {
    await wait(250);
    const userId = this.requireUser();
    const all = this.db.deliveries
      .filter((d) => d.userId === userId)
      .sort((a, b) => (b.sentAt ?? '').localeCompare(a.sentAt ?? ''));
    const totalPages = Math.max(1, Math.ceil(all.length / PAGE_SIZE));
    const p = Math.min(Math.max(1, page), totalPages);
    const items = all.slice((p - 1) * PAGE_SIZE, p * PAGE_SIZE).map((d) => {
      const { userId: _owner, ...rest } = d; // eslint-disable-line @typescript-eslint/no-unused-vars
      return rest;
    });
    return { items, page: p, totalPages };
  }

  async sendSampleNews() {
    await wait(700);
    const userId = this.requireUser();
    const targets = this.db.channels.filter((c) => c.userId === userId && c.isVerified && c.isEnabled);
    const news = FAKE_NEWS[Math.floor(Math.random() * FAKE_NEWS.length)];
    for (const ch of targets) {
      this.db.deliveries.push(this.makeDelivery(userId, news, ch.channelType, new Date(), 'sent'));
    }
    this.save();
    return { delivered: targets.length, failed: 0 };
  }

  // ---------------- Admin: sources (UC-9) and pipeline status ----------------
  async adminListSources() {
    await wait(200);
    this.requireUser();
    return this.sources().map((x) => ({ ...x }));
  }

  async adminAddSource(req: AdminSourceRequest) {
    await wait();
    this.requireUser();
    const errs = this.checkSource(req);
    if (Object.keys(errs).length) throw new ApiError('Please check the highlighted fields.', 422, errs);
    if (this.sources().some((x) => x.url.toLowerCase() === req.url.trim().toLowerCase())) {
      throw new ApiError('A source with this URL is already registered.', 409, { url: 'Already registered.' });
    }
    const src: AdminSourceView = {
      sourceId: this.id(),
      name: req.name.trim(),
      sourceType: req.sourceType,
      url: req.url.trim(),
      baseWeight: req.baseWeight,
      isActive: req.isActive,
      termsUrl: req.termsUrl.trim(),
      config: req.config ?? {},
      lastCheckedAt: null,
      lastSuccessAt: null,
      consecutiveFailures: 0,
      lastError: null,
      itemCount: 0,
    };
    this.sources().push(src);
    this.save();
    return { ...src };
  }

  async adminUpdateSource(sourceId: number, changes: Partial<AdminSourceRequest>) {
    await wait();
    this.requireUser();
    const src = this.findSource(sourceId);
    const errs = this.checkSource(changes);
    if (Object.keys(errs).length) throw new ApiError('Please check the highlighted fields.', 422, errs);
    if (changes.url && this.sources().some((x) => x !== src && x.url.toLowerCase() === changes.url!.trim().toLowerCase())) {
      throw new ApiError('A source with this URL is already registered.', 409, { url: 'Already registered.' });
    }
    Object.assign(src, changes);
    this.save();
    return { ...src };
  }

  async adminDeleteSource(sourceId: number) {
    await wait();
    this.requireUser();
    const src = this.findSource(sourceId);
    if (src.itemCount > 0) {
      throw new ApiError('This source has collected news, so it cannot be removed. Turn it off instead.', 409);
    }
    this.db.adminSources = this.sources().filter((x) => x !== src);
    for (const p of Object.values(this.db.profiles)) p.followedSourceIds = p.followedSourceIds.filter((id) => id !== sourceId);
    this.save();
  }

  async adminPipelineStatus(): Promise<PipelineStatusView> {
    await wait(200);
    this.requireUser();
    const sources = this.sources();
    const newsItems = FAKE_NEWS.length;
    const high = FAKE_NEWS.filter((n) => n.level === 'high').length;
    const medium = FAKE_NEWS.filter((n) => n.level === 'medium').length;

    // A dozen recent cycles, a few minutes apart, newest first: scrape, classify, dispatch in turn.
    const types = ['scrape', 'classify', 'dispatch'] as const;
    const now = Date.now();
    const runs: CycleRunView[] = Array.from({ length: 12 }, (_, i) => {
      const cycleType = types[(11 - i) % 3];
      const startedAt = now - (i * 4 + 1) * 60 * 1000;
      const seconds = cycleType === 'scrape' ? 18 + (i % 4) * 5 : cycleType === 'classify' ? 6 + (i % 3) : 3 + (i % 2);
      const itemsProcessed = cycleType === 'scrape' ? 3 + (i % 5) : cycleType === 'classify' ? 4 + (i % 4) : 2 + (i % 3);
      const notes =
        cycleType === 'scrape'
          ? JSON.stringify({ sources: sources.filter((x) => x.isActive).length, new: itemsProcessed })
          : cycleType === 'classify'
            ? JSON.stringify({ scored: itemsProcessed })
            : null;
      return {
        runId: 100 - i,
        cycleType,
        startedAt: new Date(startedAt).toISOString(),
        finishedAt: i === 0 && cycleType === 'dispatch' ? null : new Date(startedAt + seconds * 1000).toISOString(),
        itemsProcessed,
        failures: i === 3 ? 1 : 0,
        notes,
      };
    });

    return {
      counts: {
        sources: sources.length,
        activeSources: sources.filter((x) => x.isActive).length,
        newsItems,
        unclassified: 3,
        undispatched: 5,
        duplicates: 4,
        high,
        medium,
        low: newsItems - high - medium,
        deliveriesQueued: 2,
        deliveriesSent: this.db.deliveries.filter((d) => d.status === 'sent').length + 40,
        deliveriesFailed: 1,
        deliveriesPermanentFailure: 1,
        subscribers: this.db.users.length,
        verifiedChannels: this.db.channels.filter((c) => c.isVerified).length,
      },
      runs,
    };
  }

  // ---------------- helpers ----------------
  private makeDelivery(
    userId: number,
    news: (typeof FAKE_NEWS)[number],
    channelType: ChannelType,
    when: Date,
    status: DeliveryView['status'],
  ) {
    const src = FAKE_SOURCES.find((s) => s.sourceId === news.sourceId)!;
    return {
      userId,
      deliveryId: this.id(),
      title: news.title,
      link: slugLink(news.title, news.sourceId),
      sourceName: src.name,
      importanceLevel: news.level,
      channelType,
      status,
      sentAt: status === 'queued' ? null : when.toISOString(),
    };
  }

  /** Gives a brand-new account some believable history to look at. */
  private seedHistoryIfEmpty(userId: number, channelType: ChannelType) {
    if (this.db.deliveries.some((d) => d.userId === userId)) return;
    const now = Date.now();
    FAKE_NEWS.forEach((news, i) => {
      const when = new Date(now - (i + 1) * 7.5 * 3600 * 1000);
      const status: DeliveryView['status'] = i === 4 ? 'failed' : i === 11 ? 'permanent_failure' : 'sent';
      this.db.deliveries.push(this.makeDelivery(userId, news, channelType, when, status));
    });
  }
}
