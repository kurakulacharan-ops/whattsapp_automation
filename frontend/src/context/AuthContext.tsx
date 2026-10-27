import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { getCurrentUser, login as loginRequest } from '../api/auth';
import type { AccountRole } from '../types';

interface AuthContextValue {
  token: string | null;
  role: AccountRole | null;
  roleLoading: boolean;
  canManage: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // Read from localStorage on mount so a page refresh doesn't boot the user
  // out — the token itself is still validated server-side on every request
  // via the 401 interceptor in api/client.ts.
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('access_token'));
  const [role, setRole] = useState<AccountRole | null>(null);
  const [roleLoading, setRoleLoading] = useState(() => !!localStorage.getItem('access_token'));

  useEffect(() => {
    if (!token) return;
    let active = true;
    getCurrentUser()
      .then((user) => {
        if (active) {
          setRole(user.role);
        }
      })
      .catch(() => {
        if (active) {
          setRole(null);
        }
      })
      .finally(() => {
        if (active) setRoleLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token]);

  const login = useCallback(async (username: string, password: string) => {
    const { access_token, role } = await loginRequest(username, password);
    localStorage.setItem('access_token', access_token);
    setRole(role);
    setRoleLoading(false);
    setToken(access_token);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('access_token');
    setToken(null);
    setRole(null);
    setRoleLoading(false);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        token,
        role,
        roleLoading,
        canManage: role === 'super_admin' || role === 'manual_team',
        isAuthenticated: !!token,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
