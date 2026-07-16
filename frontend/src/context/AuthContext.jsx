// src/context/AuthContext.jsx
import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import * as authApi from "../api/auth";

const AuthContext = createContext();
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("token"));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Validate an existing token on mount
  useEffect(() => {
    let active = true;
    (async () => {
      if (!token) { setLoading(false); return; }
      try {
        const me = await authApi.getMe();
        if (active) setUser(me);
      } catch {
        localStorage.removeItem("token");
        if (active) { setToken(null); setUser(null); }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
    // eslint-disable-next-line
  }, []);

  const _apply = (res) => {
    localStorage.setItem("token", res.token);
    setToken(res.token);
    setUser(res.user);
    return res.user;
  };

  const login = useCallback(async (email, password) => {
    const res = await authApi.login(email, password);
    return _apply(res);
  }, []);

  const register = useCallback(async (email, password, profile) => {
    const res = await authApi.register(email, password, profile);
    _apply(res);
    return res;   // includes { user, token, email_sent }
  }, []);

  const updateProfile = useCallback(async (fields) => {
    const updated = await authApi.updateProfile(fields);
    setUser(updated);
    return updated;
  }, []);

  const refreshUser = useCallback(async () => {
    const me = await authApi.getMe();
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, loading, isAuthenticated: !!token, login, register, updateProfile, refreshUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
