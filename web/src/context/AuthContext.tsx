import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { api } from '../api';
import type { AccountView } from '../types';

interface AuthState {
  account: AccountView | null;
  loading: boolean;
  register(email: string, password: string): Promise<AccountView>;
  login(email: string, password: string): Promise<AccountView>;
  logout(): Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<AccountView | null>(null);
  const [loading, setLoading] = useState(true);

  // On first load, ask the server who we are (the 7-day session cookie, Change 7).
  useEffect(() => {
    api
      .me()
      .then(setAccount)
      .catch(() => setAccount(null))
      .finally(() => setLoading(false));
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const a = await api.register(email, password);
    setAccount(a);
    return a;
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const a = await api.login(email, password);
    setAccount(a);
    return a;
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setAccount(null);
  }, []);

  return <AuthContext.Provider value={{ account, loading, register, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
