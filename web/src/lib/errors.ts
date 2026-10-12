import { ApiError } from '../api';

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return 'Something went wrong.';
}

export function fieldErrors(e: unknown): Record<string, string> {
  return e instanceof ApiError ? e.fieldErrors : {};
}
