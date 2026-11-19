import type { ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AppLayout } from './components/AppLayout';
import { PageSpinner } from './components/ui';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import AdminPipelinePage from './pages/AdminPipelinePage';
import AdminSourcesPage from './pages/AdminSourcesPage';
import ChannelSetupPage from './pages/ChannelSetupPage';
import DashboardPage from './pages/DashboardPage';
import HistoryPage from './pages/HistoryPage';
import LandingPage from './pages/LandingPage';
import LoginPage from './pages/LoginPage';
import NotificationsPage from './pages/NotificationsPage';
import RegisterPage from './pages/RegisterPage';

/** Sends signed-out visitors to the login page, then back where they wanted to go. */
function RequireAuth({ children }: { children: ReactNode }) {
  const { account, loading } = useAuth();
  const location = useLocation();
  if (loading) return <PageSpinner />;
  if (!account) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

/** Admin-only pages: everyone else goes back to the dashboard. */
function RequireAdmin({ children }: { children: ReactNode }) {
  const { account } = useAuth();
  if (account?.role !== 'admin') return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

/** Signed-in users skip the login and sign-up pages. */
function GuestOnly({ children }: { children: ReactNode }) {
  const { account, loading } = useAuth();
  if (loading) return <PageSpinner />;
  if (account) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/signup" element={<GuestOnly><RegisterPage /></GuestOnly>} />
            <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
            <Route path="/setup" element={<RequireAuth><ChannelSetupPage /></RequireAuth>} />
            <Route path="/dashboard" element={<RequireAuth><AppLayout /></RequireAuth>}>
              <Route index element={<DashboardPage />} />
              <Route path="notifications" element={<NotificationsPage />} />
              <Route path="history" element={<HistoryPage />} />
              <Route path="admin/sources" element={<RequireAdmin><AdminSourcesPage /></RequireAdmin>} />
              <Route path="admin/pipeline" element={<RequireAdmin><AdminPipelinePage /></RequireAdmin>} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
