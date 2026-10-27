import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export function ProtectedRoute({ requireManualTeam = false }: { requireManualTeam?: boolean }) {
  const { isAuthenticated, canManage, roleLoading } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (requireManualTeam && roleLoading) return <p className="p-8 text-sm">Loading account permissions…</p>;
  if (requireManualTeam && !canManage) return <Navigate to="/attendance" replace />;
  return <Outlet />;
}
