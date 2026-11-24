/*
 * Who is signed in, for the whole component tree (React Context).
 *
 *   const { user, isAuthed, login, logout, ... } = useAuth();
 *
 * The source of truth is the session in localStorage (api/client.js); this provider
 * mirrors it into React state so components re-render when the user signs in or out,
 * and exposes the auth actions.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import * as client from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => client.session.user());

  // keep React state in sync with the stored session (login, logout, token refresh, other tab)
  useEffect(() => {
    const unsubscribe = client.session.subscribe(setUser);
    const onStorage = (e) => { if (e.key === null || e.key.startsWith("rh.")) setUser(client.session.user()); };
    window.addEventListener("storage", onStorage);
    return () => { unsubscribe(); window.removeEventListener("storage", onStorage); };
  }, []);

  // refresh the profile once per page load, so counters and the role are current
  useEffect(() => {
    if (client.session.isAuthed()) client.reloadUser().catch(() => { /* handled by api(): 401 clears the session */ });
  }, []);

  const login = useCallback((username, password) => client.login(username, password), []);
  const register = useCallback((payload) => client.register(payload), []);
  const logout = useCallback(() => client.logout(), []);
  const reload = useCallback(() => client.reloadUser(), []);

  const value = useMemo(() => ({
    user,
    isAuthed: Boolean(user && client.session.access()),
    hasRole: (...roles) => Boolean(user && roles.includes(user.role)),
    canCreateLectures: Boolean(user && (user.role === "lecturer" || user.role === "admin")),
    claims: () => client.session.claims(),
    login, register, logout, reload,
    refreshTokens: client.refreshTokens,
    saveSession: (data) => client.session.save(data),
  }), [user, login, register, logout, reload]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() must be used inside <AuthProvider>");
  return ctx;
}
