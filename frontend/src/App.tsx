import { Navigate, Route, Routes } from "react-router-dom";
import { Masthead } from "@/components/Masthead";
import { SignInPage } from "@/pages/SignIn";
import { DashboardPage } from "@/pages/Dashboard";
import { WorkspacePage } from "@/pages/Workspace";
import { TreasuryPage } from "@/pages/Treasury";
import { AuditPage } from "@/pages/Audit";
import { SettingsPage } from "@/pages/Settings";
import { useAuthStore } from "@/store/auth";

function RequireAuth({ children }: { children: JSX.Element }) {
  const token = useAuthStore((s) => s.accessToken);
  if (!token) return <Navigate to="/signin" replace />;
  return children;
}

export function App(): JSX.Element {
  const token = useAuthStore((s) => s.accessToken);

  return (
    <div className="min-h-screen flex flex-col">
      {token && <Masthead />}
      <main className="flex-1">
        <Routes>
          <Route path="/signin" element={<SignInPage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <DashboardPage />
              </RequireAuth>
            }
          />
          <Route
            path="/sessions/:id"
            element={
              <RequireAuth>
                <WorkspacePage />
              </RequireAuth>
            }
          />
          <Route
            path="/treasury"
            element={
              <RequireAuth>
                <TreasuryPage />
              </RequireAuth>
            }
          />
          <Route
            path="/audit"
            element={
              <RequireAuth>
                <AuditPage />
              </RequireAuth>
            }
          />
          <Route
            path="/settings"
            element={
              <RequireAuth>
                <SettingsPage />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <footer className="border-t border-rule py-6 text-center font-ui text-xs text-sub">
        ATRIO Boardroom — your AI boardroom · Milan AI Week 2026
      </footer>
    </div>
  );
}
