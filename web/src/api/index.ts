import type { ApiClient } from './ApiClient';
import { HttpApiClient } from './HttpApiClient';
import { MockApiClient } from './MockApiClient';

export { ApiError } from './ApiClient';
export type { ApiClient } from './ApiClient';

// One shared client for the whole app. Pick the mode in .env:
//   VITE_API_MODE=mock  -> fake data, no server
//   VITE_API_MODE=live  -> FastAPI server through the /api proxy
const mode = (import.meta.env.VITE_API_MODE ?? 'mock') as 'mock' | 'live';

export const api: ApiClient = mode === 'live' ? new HttpApiClient(import.meta.env.VITE_API_BASE ?? '/api') : new MockApiClient();
